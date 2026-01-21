from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Optional

import httpx
from pydantic import BaseModel, Field, ValidationError

from metta.app_backend.config import settings


class SmartPlugDevice(BaseModel):
    key: str
    label: str
    alias: Optional[str] = None
    device_id: str
    channel: int = Field(default=0, ge=0)


class SmartPlugStatus(BaseModel):
    key: str
    label: str
    alias: Optional[str] = None
    online: Optional[bool] = None
    is_on: Optional[bool] = None
    apower: Optional[float] = None


class _SmartPlugConfig(BaseModel):
    plugs: list[SmartPlugDevice]
    server_host: Optional[str] = None
    auth_key: Optional[str] = None


RATE_LIMIT_SECONDS = 1.0
REQUEST_TIMEOUT_SECONDS = 10.0

_config_cache: _SmartPlugConfig | None = None
_config_payload: str | None = None


class _RateLimiter:
    def __init__(self, min_interval_seconds: float) -> None:
        self._min_interval = max(min_interval_seconds, 0.0)
        self._lock = asyncio.Lock()
        self._next_allowed = 0.0

    async def wait(self) -> None:
        if self._min_interval <= 0:
            return
        async with self._lock:
            now = time.monotonic()
            if now < self._next_allowed:
                await asyncio.sleep(self._next_allowed - now)
            self._next_allowed = time.monotonic() + self._min_interval


_rate_limiter = _RateLimiter(RATE_LIMIT_SECONDS)


def _parse_config(payload: Any) -> _SmartPlugConfig:
    if isinstance(payload, list):
        payload = {"plugs": payload}
    if not isinstance(payload, dict):
        raise ValueError("Smart plug config must be a list or object with 'plugs'")
    try:
        parsed = _SmartPlugConfig(**payload)
    except ValidationError as exc:
        raise ValueError(f"Invalid smart plug config: {exc}") from exc
    if not parsed.plugs:
        raise ValueError("Smart plug config is empty")
    return parsed


def _get_config() -> _SmartPlugConfig:
    global _config_cache, _config_payload

    if not settings.SMART_PLUGS_ENABLED:
        raise RuntimeError("Smart plugs are disabled")

    payload = settings.SMART_PLUGS_CONFIG_JSON
    if not payload:
        raise RuntimeError("Smart plug config is not configured")

    if _config_cache is None or _config_payload != payload:
        _config_cache = _parse_config(json.loads(payload))
        _config_payload = payload
    return _config_cache


def _get_device(key: str) -> SmartPlugDevice:
    devices = {device.key: device for device in _get_config().plugs}
    if key not in devices:
        raise KeyError(f"Unknown smart plug key: {key}")
    return devices[key]


def _build_url(endpoint: str) -> str:
    config = _get_config()
    if not config.server_host:
        raise RuntimeError("Smart plug server host is not configured")
    if not config.auth_key:
        raise RuntimeError("Smart plug auth key is not configured")
    return f"{config.server_host}/v2/devices/api/{endpoint}?auth_key={config.auth_key}"


async def _post(endpoint: str, payload: dict[str, Any]) -> Any:
    await _rate_limiter.wait()
    url = _build_url(endpoint)
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        response = await client.post(url, json=payload)
    response.raise_for_status()
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return {}


def _extract_switch_status(status: Any, channel: int) -> dict[str, Any] | None:
    if not isinstance(status, dict):
        return None
    switch_value = status.get(f"switch:{channel}", status.get("switch"))
    if isinstance(switch_value, list):
        return switch_value[channel] if 0 <= channel < len(switch_value) else None
    if isinstance(switch_value, dict):
        return switch_value
    return None


async def fetch_statuses(keys: Optional[list[str]] = None) -> list[SmartPlugStatus]:
    config = _get_config()
    device_map = {device.key: device for device in config.plugs}
    devices = list(config.plugs)

    if keys is not None:
        unknown = [key for key in keys if key not in device_map]
        if unknown:
            raise KeyError(f"Unknown smart plug keys: {', '.join(unknown)}")
        devices = [device_map[key] for key in keys]

    payload = {"ids": [device.device_id for device in devices], "select": ["status"]}
    response = await _post("get", payload)

    status_by_id = (
        {item["id"]: item for item in response if isinstance(item, dict) and item.get("id")}
        if isinstance(response, list)
        else {}
    )

    results: list[SmartPlugStatus] = []
    for device in devices:
        raw = status_by_id.get(device.device_id, {})
        status = raw.get("status", {})
        switch_status = _extract_switch_status(status, device.channel)
        is_on = None
        apower = None
        if isinstance(switch_status, dict):
            is_on = switch_status.get("output")
            apower = switch_status.get("apower")
        results.append(
            SmartPlugStatus(
                key=device.key,
                label=device.label,
                alias=device.alias,
                online=raw.get("online"),
                is_on=is_on,
                apower=apower,
            )
        )
    return results


async def set_power(key: str, on: bool, toggle_after: Optional[int] = None) -> None:
    device = _get_device(key)

    payload: dict[str, Any] = {"id": device.device_id, "on": on, "channel": device.channel}
    if toggle_after is not None:
        payload["toggle_after"] = toggle_after

    await _post("set/switch", payload)
