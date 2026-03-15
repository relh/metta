from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from recipes.experiment import machina_1


def _entry(*, rank: int, name: str, policy_id: str | None):
    return SimpleNamespace(
        rank=rank,
        policy=SimpleNamespace(name=name, id=None if policy_id is None else uuid.UUID(policy_id)),
    )


def _make_fake_env() -> SimpleNamespace:
    return SimpleNamespace(
        game=SimpleNamespace(
            vibe_names=[],
            actions=SimpleNamespace(change_vibe=SimpleNamespace(vibes=[])),
            agent=SimpleNamespace(vibe=0),
            max_steps=0,
        )
    )


def test_lookup_default_teacher_policy_uri_uses_top_ranked_dinky(monkeypatch: pytest.MonkeyPatch) -> None:
    leaderboard = [
        _entry(rank=1, name="slanky", policy_id="11111111-1111-1111-1111-111111111111"),
        _entry(rank=3, name="dinky", policy_id="33333333-3333-3333-3333-333333333333"),
        _entry(rank=2, name="dinky", policy_id="22222222-2222-2222-2222-222222222222"),
    ]
    calls: list[tuple[str, str]] = []

    class FakeClient:
        def __init__(self, *, server_url: str):
            self.server_url = server_url

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, exc_type, exc_val, exc_tb) -> None:
            return None

        def get_leaderboard(self, season_name: str):
            calls.append((self.server_url, season_name))
            return leaderboard

    monkeypatch.setattr(machina_1, "auto_stats_server_uri", lambda: None)
    monkeypatch.setattr(machina_1, "TournamentServerClient", FakeClient)

    teacher_uri = machina_1._lookup_default_teacher_policy_uri()

    assert teacher_uri == "metta://policy/22222222-2222-2222-2222-222222222222"
    assert calls == [(machina_1.DEFAULT_TEACHER_SERVER_URL, machina_1.DEFAULT_TEACHER_SEASON)]


def test_lookup_default_teacher_policy_uri_prefers_configured_stats_server(monkeypatch: pytest.MonkeyPatch) -> None:
    leaderboard = [_entry(rank=1, name="dinky", policy_id="22222222-2222-2222-2222-222222222222")]
    calls: list[tuple[str, str]] = []

    class FakeClient:
        def __init__(self, *, server_url: str):
            self.server_url = server_url

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, exc_type, exc_val, exc_tb) -> None:
            return None

        def get_leaderboard(self, season_name: str):
            calls.append((self.server_url, season_name))
            return leaderboard

    monkeypatch.setattr(machina_1, "auto_stats_server_uri", lambda: "https://staging.observatory.example")
    monkeypatch.setattr(machina_1, "TournamentServerClient", FakeClient)

    teacher_uri = machina_1._lookup_default_teacher_policy_uri()

    assert teacher_uri == "metta://policy/22222222-2222-2222-2222-222222222222"
    assert calls == [("https://staging.observatory.example", machina_1.DEFAULT_TEACHER_SEASON)]


def test_lookup_default_teacher_policy_uri_requires_ranked_dinky(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        def __init__(self, *, server_url: str):
            self.server_url = server_url

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, exc_type, exc_val, exc_tb) -> None:
            return None

        def get_leaderboard(self, season_name: str):
            _ = season_name
            return [_entry(rank=1, name="slanky", policy_id="11111111-1111-1111-1111-111111111111")]

    monkeypatch.setattr(machina_1, "auto_stats_server_uri", lambda: None)
    monkeypatch.setattr(machina_1, "TournamentServerClient", FakeClient)

    with pytest.raises(RuntimeError, match="Could not find policy 'dinky' on the beta-cvc leaderboard"):
        machina_1._lookup_default_teacher_policy_uri()


def test_train_use_default_teacher_resolves_current_dinky(monkeypatch: pytest.MonkeyPatch) -> None:
    teacher_uri = "metta://policy/22222222-2222-2222-2222-222222222222"

    def fake_train_single_mission(*, teacher=None, **kwargs):
        _ = kwargs
        training_env = SimpleNamespace(
            supervisor_policy_uri=None if teacher is None else teacher.policy_uri,
            curriculum=SimpleNamespace(task_generator=SimpleNamespace(env=_make_fake_env())),
        )
        return SimpleNamespace(
            policy_assets={"learner0": SimpleNamespace(architecture=None)},
            system=SimpleNamespace(torch_deterministic=True),
            training_env=training_env,
            evaluator=SimpleNamespace(simulations=[], epoch_interval=None),
        )

    monkeypatch.setattr(machina_1, "_lookup_default_teacher_policy_uri", lambda: teacher_uri)
    monkeypatch.setattr(machina_1, "train_single_mission", fake_train_single_mission)
    monkeypatch.setattr(machina_1, "make_training_env", lambda **kwargs: _make_fake_env())
    monkeypatch.setattr(machina_1, "SimulationConfig", lambda **kwargs: SimpleNamespace(**kwargs))

    tool = machina_1.train(use_default_teacher=True)

    assert tool.training_env.supervisor_policy_uri == teacher_uri
