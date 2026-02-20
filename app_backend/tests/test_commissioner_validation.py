from __future__ import annotations

from abc import ABC, abstractmethod

import pytest

from metta.app_backend.tournament.commissioners.base import CommissionerBase


def _make_concrete_commissioner(
    *,
    referees: dict[str, object] | None = None,
    season_name: str = "test",
    display_name: str | None = "Test",
    entry_pool: str | None = None,
    leaderboard_pool: str | None = None,
) -> type:
    attrs: dict[str, object] = {
        "season_name": season_name,
        "referees": referees if referees is not None else {},
        "get_new_submission_membership_changes": lambda self, pv_id: [],
        "get_membership_changes": lambda self, pools: [],
    }
    if display_name is not None:
        attrs["display_name"] = display_name
    if entry_pool is not None:
        attrs["entry_pool"] = entry_pool
    if leaderboard_pool is not None:
        attrs["leaderboard_pool"] = leaderboard_pool
    return type("_Dynamic", (CommissionerBase,), attrs)


def test_valid_subclass():
    cls = _make_concrete_commissioner(
        referees={"qualifying": object(), "ranked": object()},
        entry_pool="qualifying",
        leaderboard_pool="ranked",
    )
    assert cls.entry_pool == "qualifying"
    assert cls.leaderboard_pool == "ranked"


def test_invalid_entry_pool_raises():
    with pytest.raises(ValueError, match="entry_pool.*not in referees"):
        _make_concrete_commissioner(
            referees={"ranked": object()},
            entry_pool="nonexistent",
            leaderboard_pool="ranked",
        )


def test_invalid_leaderboard_pool_raises():
    with pytest.raises(ValueError, match="leaderboard_pool.*not in referees"):
        _make_concrete_commissioner(
            referees={"qualifying": object()},
            entry_pool="qualifying",
            leaderboard_pool="nonexistent",
        )


def test_abstract_subclass_skips_validation():
    class _AbstractCommissioner(CommissionerBase, ABC):
        season_name = "test"
        referees: dict[str, object] = {"a": object()}
        entry_pool = "wrong"
        leaderboard_pool = "also-wrong"

        @abstractmethod
        def extra(self) -> None: ...

    assert _AbstractCommissioner.entry_pool == "wrong"


def test_missing_display_name_raises():
    with pytest.raises(ValueError, match="display_name must be a non-empty string"):
        _make_concrete_commissioner(display_name=None)


def test_display_name_can_be_overridden():
    cls = _make_concrete_commissioner(season_name="beta-cvc", display_name="Beta CvC")
    assert cls.display_name == "Beta CvC"
