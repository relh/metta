from __future__ import annotations

from devops.datadog.cli import (
    PruneMode,
    _dry_run_prune_summary,
    _managed_monitors_missing_from_code,
    _should_delete_candidates,
)


def test_managed_monitors_missing_from_code_filters_and_sorts() -> None:
    monitors = [
        {"id": 10, "name": "z-manual", "tags": []},
        {"id": 11, "name": "b-managed-extra", "tags": ["managed-by:code"]},
        {"id": 12, "name": "a-managed-expected", "tags": ["managed-by:code"]},
        {"id": 13, "name": "c-managed-extra", "tags": ["managed-by:code", "scope:testing"]},
    ]
    expected_names = {"a-managed-expected"}

    candidates = _managed_monitors_missing_from_code(monitors, expected_names)

    assert [candidate["id"] for candidate in candidates] == [11, 13]
    assert [candidate["name"] for candidate in candidates] == ["b-managed-extra", "c-managed-extra"]


def test_should_delete_candidates_honors_prune_mode() -> None:
    assert _should_delete_candidates(PruneMode.YES) is True
    assert _should_delete_candidates(PruneMode.NO) is False
    assert _should_delete_candidates(PruneMode.ASK) is None


def test_dry_run_prune_summary_describes_mode() -> None:
    assert _dry_run_prune_summary(PruneMode.YES, 3) == (
        "Dry-run prune behavior: would delete these candidates (prune=yes)."
    )
    assert _dry_run_prune_summary(PruneMode.NO, 3) == (
        "Dry-run prune behavior: would not delete these candidates (prune=no)."
    )
    assert _dry_run_prune_summary(PruneMode.ASK, 3) == (
        "Dry-run prune behavior: would prompt before deleting these candidates (prune=ask)."
    )
    assert _dry_run_prune_summary(PruneMode.ASK, 0) == ("Dry-run prune behavior: no candidates (prune=ask).")
