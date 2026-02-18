"""EC2 pricing lookup for job cost metrics.

Fetches actual pricing from AWS APIs with TTL caches:
- On-demand: AWS Pricing API, cached 24h
- Spot: EC2 describe_spot_price_history, cached 1h

Design notes:
- try/except around AWS API calls is intentional: these are external service
  boundaries where transient failures are expected. We serve stale cached prices
  rather than crashing the request handler.
- Dict caches are read/written without locks. Under CPython's GIL, dict.get()
  and dict.__setitem__ are atomic. Worst case is a redundant API call when two
  threads both see a cache miss — harmless since both write the same value.
"""

import json
import logging
import threading
import time

import boto3
from botocore.client import BaseClient

logger = logging.getLogger(__name__)

# Region code → Pricing API location name
_REGION_LOCATIONS: dict[str, str] = {
    "us-east-1": "US East (N. Virginia)",
    "us-east-2": "US East (Ohio)",
    "us-west-1": "US West (N. California)",
    "us-west-2": "US West (Oregon)",
    "eu-west-1": "EU (Ireland)",
    "eu-central-1": "EU (Frankfurt)",
    "ap-southeast-1": "Asia Pacific (Singapore)",
    "ap-northeast-1": "Asia Pacific (Tokyo)",
}

# On-demand cache: (instance_type, region) → (price, fetch_time)
_on_demand_cache: dict[tuple[str, str], tuple[float, float]] = {}
_ON_DEMAND_TTL_SECONDS = 86400  # 24 hours

# Spot price cache: (instance_type, region) → (price, fetch_time)
_spot_cache: dict[tuple[str, str], tuple[float, float]] = {}
_SPOT_TTL_SECONDS = 3600  # 1 hour

_ec2_clients: dict[str, BaseClient] = {}
_ec2_clients_lock = threading.Lock()

_pricing_client: BaseClient | None = None
_pricing_client_lock = threading.Lock()


def _get_ec2_client(region: str) -> BaseClient:
    """Get or create an EC2 client for the given region. Thread-safe, per-region cache."""
    client = _ec2_clients.get(region)
    if client is not None:
        return client
    with _ec2_clients_lock:
        client = _ec2_clients.get(region)
        if client is not None:
            return client
        client = boto3.client("ec2", region_name=region)
        _ec2_clients[region] = client
        return client


def _get_pricing_client() -> BaseClient:
    """Pricing API is only available in us-east-1 and ap-south-1."""
    global _pricing_client
    if _pricing_client is None:
        with _pricing_client_lock:
            if _pricing_client is None:
                _pricing_client = boto3.client("pricing", region_name="us-east-1")
    return _pricing_client


def _fetch_on_demand_price(instance_type: str, region: str) -> float | None:
    """Fetch on-demand price from AWS Pricing API."""
    location = _REGION_LOCATIONS.get(region)
    if location is None:
        logger.warning(f"No pricing location mapping for region {region}")
        return None

    client = _get_pricing_client()
    response = client.get_products(
        ServiceCode="AmazonEC2",
        Filters=[
            {"Type": "TERM_MATCH", "Field": "instanceType", "Value": instance_type},
            {"Type": "TERM_MATCH", "Field": "location", "Value": location},
            {"Type": "TERM_MATCH", "Field": "operatingSystem", "Value": "Linux"},
            {"Type": "TERM_MATCH", "Field": "preInstalledSw", "Value": "NA"},
            {"Type": "TERM_MATCH", "Field": "tenancy", "Value": "Shared"},
            {"Type": "TERM_MATCH", "Field": "capacitystatus", "Value": "Used"},
        ],
        MaxResults=1,
    )

    price_list = response.get("PriceList", [])
    if not price_list:
        return None

    product = json.loads(price_list[0])
    on_demand = product.get("terms", {}).get("OnDemand", {})
    for term in on_demand.values():
        for dimension in term.get("priceDimensions", {}).values():
            if dimension.get("unit") != "Hrs":
                continue
            price_str = dimension.get("pricePerUnit", {}).get("USD")
            if price_str:
                price = float(price_str)
                if price > 0:
                    return price
    return None


def _get_on_demand_price(instance_type: str, region: str) -> float | None:
    """Get on-demand price with 24h TTL cache. Serves stale price on API failure."""
    key = (instance_type, region)
    cached = _on_demand_cache.get(key)
    if cached is not None:
        price, fetch_time = cached
        if time.monotonic() - fetch_time < _ON_DEMAND_TTL_SECONDS:
            return price

    try:
        price = _fetch_on_demand_price(instance_type, region)
    except Exception:
        logger.warning(f"Failed to fetch on-demand price for {instance_type} in {region}")
        price = None

    if price is not None:
        _on_demand_cache[key] = (price, time.monotonic())
        return price

    # API failed or returned None — serve stale cached price if available
    if cached is not None:
        logger.info(f"Serving stale on-demand price for {instance_type} in {region}")
        return cached[0]
    return None


def _fetch_spot_price(instance_type: str, region: str) -> float | None:
    """Fetch current spot price from EC2 API.

    Returns max price across AZs for the most recent timestamp only,
    avoiding historical spikes from older entries.
    """
    client = _get_ec2_client(region)
    response = client.describe_spot_price_history(
        InstanceTypes=[instance_type],
        ProductDescriptions=["Linux/UNIX"],
        MaxResults=10,
    )
    history = response.get("SpotPriceHistory", [])
    if not history:
        return None

    # Results are sorted newest-first. Take only entries matching the most recent timestamp.
    latest_ts = history[0]["Timestamp"]
    prices = [float(r["SpotPrice"]) for r in history if r["Timestamp"] == latest_ts]
    return max(prices)


def _get_spot_price(instance_type: str, region: str) -> float | None:
    """Get spot price with 1h TTL cache. Serves stale price on API failure."""
    key = (instance_type, region)
    cached = _spot_cache.get(key)
    if cached is not None:
        price, fetch_time = cached
        if time.monotonic() - fetch_time < _SPOT_TTL_SECONDS:
            return price

    try:
        price = _fetch_spot_price(instance_type, region)
    except Exception:
        logger.warning(f"Failed to fetch spot price for {instance_type} in {region}")
        price = None

    if price is not None:
        _spot_cache[key] = (price, time.monotonic())
        return price

    # API failed or returned None — serve stale cached price if available
    if cached is not None:
        logger.info(f"Serving stale spot price for {instance_type} in {region}")
        return cached[0]
    return None


def get_instance_hourly_cost(
    instance_type: str | None,
    capacity_type: str | None,
    region: str = "us-east-1",
) -> float:
    """Look up the hourly cost for an EC2 instance.

    - "spot": cached spot price (1h TTL), falls back to on-demand if API fails
    - "on-demand" or None: cached on-demand from Pricing API (24h TTL)
    - Unknown instance_type or all API failures: returns 0.0
    """
    if instance_type is None:
        return 0.0

    if capacity_type == "spot":
        spot_price = _get_spot_price(instance_type, region)
        if spot_price is not None:
            return spot_price
        logger.warning(f"Spot price unavailable for {instance_type}, falling back to on-demand")

    on_demand_price = _get_on_demand_price(instance_type, region)
    if on_demand_price is not None:
        return on_demand_price

    return 0.0
