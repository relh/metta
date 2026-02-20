"""Shared KPI math for state-page backend and dashboard consumers."""

from collections.abc import Mapping

RESOURCES = ["carbon", "heart", "oxygen", "silicon", "germanium"]


def safe_div(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b > 0 else default


def action_success_total(metrics: Mapping[str, float]) -> float:
    return sum(value for key, value in metrics.items() if key.startswith("action.") and key.endswith(".success"))


def move_efficiency(metrics: Mapping[str, float]) -> float:
    move_success = float(metrics.get("action.move.success", 0))
    move_failed = float(metrics.get("action.move.failed", 0))
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
    aligned = float(metrics.get("junction.aligned_by_agent", 0))
    scrambled = float(metrics.get("junction.scrambled_by_agent", 0))
    return safe_div(aligned, aligned + scrambled)


def noop_rate(metrics: Mapping[str, float]) -> float:
    noop = float(metrics.get("action.noop.success", 0))
    failed = float(metrics.get("action.failed", 0))
    total = action_success_total(metrics) + failed
    return safe_div(noop, total)
