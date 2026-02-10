from __future__ import annotations

from metta.abtest.experiment import ABExperiment, create_experiment


def experiment() -> ABExperiment:
    # Example experiment definition consumed by tools/run_ab_test.py
    return (
        create_experiment(
            name="example_lr_ab",
            description="Compare two learning rates with identical seeds + grouping.",
            tool="train arena",
        )
        .set_runs_per_variant(2)
        .set_base_overrides(
            trainer__total_timesteps=10000,
            training_env__vectorization="serial",
            system__local_only=True,
        )
        .set_wandb(project="metta", entity=None, tags=["ab_example"])
        .add_variant(name="lr_1e-3", trainer__optimizer__lr=1e-3)
        .add_variant(name="lr_1e-4", trainer__optimizer__lr=1e-4)
        .build()
    )
