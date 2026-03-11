from __future__ import annotations

import json
from urllib.request import Request, urlopen

from devops.runners.metta_constants import PROD_STATS_SERVER_URI
from devops.stable.stable_check_context import StableCheckContext
from devops.stable.stable_check_groups import StableCheckGroup
from devops.stable.stable_function_check_registry import stable_function_check

ALIGNMENTLEAGUE_URL = "https://softmax.com/alignmentleague"
HEALTH_URL = "https://softmax.com/api/health"
SEASONS_URL = f"{PROD_STATS_SERVER_URI}/tournament/seasons"


def _get(url: str, *, timeout_s: float = 15.0, user_agent: str = "metta-stable-health-check/1.0") -> tuple[int, str]:
    request = Request(url, headers={"User-Agent": user_agent})
    with urlopen(request, timeout=timeout_s) as response:
        status_code = response.getcode()
        body = response.read().decode("utf-8")
    return status_code, body


@stable_function_check(
    timeout_s=300,
    check_group=StableCheckGroup.LIVE_TESTS_LIGHT,
)
def healthcheck(_ctx: StableCheckContext) -> None:
    """Verify softmax.com/alignmentleague, the /api/health endpoint, and the tournament seasons API are all healthy."""
    page_status, page_body = _get(ALIGNMENTLEAGUE_URL)
    assert page_status == 200, f"{ALIGNMENTLEAGUE_URL} returned {page_status}, expected 200"
    assert page_body.strip(), f"{ALIGNMENTLEAGUE_URL} returned an empty response body"

    health_status, health_body = _get(HEALTH_URL)
    assert health_status == 200, f"{HEALTH_URL} returned {health_status}, expected 200"
    health_payload = json.loads(health_body)
    assert health_payload["status"] == "healthy", f"{HEALTH_URL} status={health_payload['status']!r}"
    assert health_payload["database"] == "connected", f"{HEALTH_URL} database={health_payload['database']!r}"

    seasons_status, seasons_body = _get(SEASONS_URL)
    assert seasons_status == 200, f"{SEASONS_URL} returned {seasons_status}, expected 200"
    seasons_payload = json.loads(seasons_body)
    assert isinstance(seasons_payload, list), f"{SEASONS_URL} did not return a list"
    assert len(seasons_payload) > 0, f"{SEASONS_URL} returned an empty list"
    first_season = seasons_payload[0]
    assert isinstance(first_season, dict), f"{SEASONS_URL} season item is not an object: {type(first_season)}"
    assert first_season["name"], f"{SEASONS_URL} first season missing name"
