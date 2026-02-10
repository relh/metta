from datetime import datetime, timezone

from metta.abtest.experiment import ABExperiment, ABVariant, materialize_runs


def test_materialize_runs_is_deterministic():
    exp = ABExperiment(
        name="exp",
        tool=["train", "arena"],
        variants=[
            ABVariant(name="a", overrides={"trainer__optimizer__lr": 1e-3}),
            ABVariant(name="b", overrides={"trainer__optimizer__lr": 1e-4}),
        ],
        runs_per_variant=2,
        base_overrides={"trainer__total_timesteps": 10},
        tags=["t1"],
    )

    now = datetime(2026, 2, 5, tzinfo=timezone.utc)
    runs1 = materialize_runs(exp, now=now)
    runs2 = materialize_runs(exp, now=now)
    assert runs1 == runs2

    assert len(runs1) == 4
    assert runs1[0].run_id.startswith("ab.exp.20260205.")
    assert any("trainer.optimizer.lr=0.001" in a for a in runs1[0].args)
    assert any("wandb.tags" in a for a in runs1[0].args)


def _wandb_tags(run_args: list[str]) -> list[str]:
    import json  # noqa: PLC0415

    tag_arg = next(a for a in run_args if a.startswith("wandb.tags="))
    return json.loads(tag_arg.split("=", 1)[1])


def test_materialize_runs_includes_variant_tags() -> None:
    exp = ABExperiment(
        name="exp",
        tool=["train", "arena"],
        variants=[
            ABVariant(name="a", tags=["va"], overrides={"trainer__optimizer__lr": 1e-3}),
            ABVariant(name="b", tags=["vb"], overrides={"trainer__optimizer__lr": 1e-4}),
        ],
        runs_per_variant=1,
        base_overrides={"trainer__total_timesteps": 10},
        tags=["t1"],
    )

    now = datetime(2026, 2, 5, tzinfo=timezone.utc)
    runs = materialize_runs(exp, now=now)
    tags_a = _wandb_tags(runs[0].args)
    tags_b = _wandb_tags(runs[1].args)
    assert tags_a == ["t1", "va", "ab_variant:a"]
    assert tags_b == ["t1", "vb", "ab_variant:b"]


def test_materialize_runs_preserves_variant_tag_with_overrides() -> None:
    exp = ABExperiment(
        name="exp",
        tool=["train", "arena"],
        variants=[
            ABVariant(name="a", overrides={"wandb__tags": ["user"], "trainer__optimizer__lr": 1e-3}),
            ABVariant(name="b", overrides={"trainer__optimizer__lr": 1e-4}),
        ],
        runs_per_variant=1,
        base_overrides={"trainer__total_timesteps": 10},
        tags=["t1"],
    )

    now = datetime(2026, 2, 5, tzinfo=timezone.utc)
    runs = materialize_runs(exp, now=now)
    tags_a = _wandb_tags(runs[0].args)
    assert "ab_variant:a" in tags_a
    assert "user" in tags_a
