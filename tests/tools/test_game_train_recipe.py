import pytest

from metta.cogworks.curriculum import Curriculum
from metta.games.games import make_game
from recipes.game import cogs_vs_clips, cogsguard, hunger


def test_hunger_train_uses_default_steps_when_max_steps_omitted() -> None:
    tool = hunger.train(num_agents=8, max_steps=None)
    env_cfg = Curriculum(tool.training_env.curriculum).get_task().get_env_cfg()
    assert env_cfg.game.max_steps == hunger.DEFAULT_MAX_TRAIN_STEPS


class _FakeTournamentGame:
    def __init__(self, num_agents: int):
        self.num_agents = num_agents

    def generate(self, seed: int):
        assert seed == 0
        return make_game("hunger", num_agents=self.num_agents, max_steps=10_000)


def _patch_tournament_game(
    monkeypatch: pytest.MonkeyPatch,
    game_name: str = "cogsguard_8agents",
    num_agents: int = 8,
) -> None:
    monkeypatch.setattr(
        cogs_vs_clips,
        "_resolve_tournament_game",
        lambda name: _FakeTournamentGame(num_agents) if name == game_name else None,
    )


def test_cogs_vs_clips_namespace_falls_back_for_train(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_tournament_game(monkeypatch)

    tool = cogs_vs_clips.train(env_name="cogsguard_8agents", max_steps=321)
    env_cfg = Curriculum(tool.training_env.curriculum).get_task().get_env_cfg()

    assert env_cfg.game.max_steps == 321
    assert tool.evaluator.simulations[0].suite == "cogsguard_8agents"


def test_cogs_vs_clips_namespace_falls_back_for_play(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_tournament_game(monkeypatch)

    tool = cogs_vs_clips.play(env_name="cogsguard_8agents", max_steps=222)
    assert tool.sim.suite == "cogsguard_8agents"
    assert tool.max_steps == 222


def test_cogs_vs_clips_rejects_variant_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_tournament_game(monkeypatch)

    with pytest.raises(ValueError, match="does not support variants overrides"):
        cogs_vs_clips.train(env_name="cogsguard_8agents", variants=["no_clips"])


def test_cogs_vs_clips_rejects_mismatched_cogs(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_tournament_game(monkeypatch)

    with pytest.raises(ValueError, match="fixed num_agents=8"):
        cogs_vs_clips.train(env_name="cogsguard_8agents", cogs=4)


def test_cogsguard_recipe_defaults_to_canonical_env_name(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    sentinel = object()

    def fake_train(**kwargs):
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(cogs_vs_clips, "train", fake_train)

    result = cogsguard.train(max_steps=123)
    assert result is sentinel
    assert captured["env_name"] == "cogsguard_8agents"
    assert captured["max_steps"] == 123
