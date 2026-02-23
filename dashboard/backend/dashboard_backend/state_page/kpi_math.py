"""Shared KPI math for state-page backend and dashboard consumers."""

from collections.abc import Mapping

RESOURCES = ["carbon", "heart", "oxygen", "silicon", "germanium"]

# Dashboard metrics historically used canonical per-agent keys. Some runs now
# surface equivalent values under simplified names; treat those as aliases.
_METRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "action.move.success": ("action.move.success", "action.move"),
    "action.move.failed": ("action.move.failed",),
    "junction.aligned_by_agent": ("junction.aligned_by_agent", "junction.aligned"),
    "junction.scrambled_by_agent": ("junction.scrambled_by_agent", "junction.scrambled"),
}


def safe_div(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b > 0 else default


def metric_value(metrics: Mapping[str, float], key: str, default: float = 0.0) -> float:
    aliases = _METRIC_ALIASES.get(key, (key,))
    for alias in aliases:
        value = metrics.get(alias)
        if isinstance(value, (int, float)):
            return float(value)
    return default


def metric_present(metrics: Mapping[str, float], key: str) -> bool:
    aliases = _METRIC_ALIASES.get(key, (key,))
    return any(alias in metrics for alias in aliases)


def metric_presence_aliases(key: str) -> tuple[str, ...]:
    return _METRIC_ALIASES.get(key, (key,))


def action_success_total(metrics: Mapping[str, float]) -> float:
    total = sum(value for key, value in metrics.items() if key.startswith("action.") and key.endswith(".success"))

    # Some runs emit total successful moves as `action.move` instead of
    # `action.move.success`. Count it once when the canonical key is absent.
    move_success = metrics.get("action.move.success")
    move_alias = metrics.get("action.move")
    if not isinstance(move_success, (int, float)) and isinstance(move_alias, (int, float)):
        total += float(move_alias)

    return total


def move_efficiency(metrics: Mapping[str, float]) -> float:
    move_success = metric_value(metrics, "action.move.success")
    move_failed = metric_value(metrics, "action.move.failed")
    return safe_div(move_success, move_success + move_failed)


def action_success_rate(metrics: Mapping[str, float]) -> float:
    failed = float(metrics.get("action.failed", 0))
    total = action_success_total(metrics) + failed
    return safe_div(total - failed, total)


def resource_retention(metrics: Mapping[str, float]) -> float:
    total_amount = sum(float(metrics.get(f"{resource}.amount", 0)) for resource in RESOURCES)
    total_gained = sum(float(metrics.get(f"{resource}.gained", 0)) for resource in RESOURCES)
    return safe_div(total_amount, total_gained)


def junction_control_rate(metrics: Mapping[str, float]) -> float:
    aligned = metric_value(metrics, "junction.aligned_by_agent")
    scrambled = metric_value(metrics, "junction.scrambled_by_agent")
    return safe_div(aligned, aligned + scrambled)


def noop_rate(metrics: Mapping[str, float]) -> float:
    noop = float(metrics.get("action.noop.success", 0))
    failed = float(metrics.get("action.failed", 0))
    total = action_success_total(metrics) + failed
    return safe_div(noop, total)
