from devops.runners.acceptance_criterion import AcceptanceCriterion
from devops.runners.core import _AcceptanceEvaluator
from devops.runners.executors.local import LocalExecutor
from devops.runners.job import Job


def test_acceptance_failures_use_metric_name_when_present() -> None:
    job = Job(
        name="training-compat",
        cmd=["true"],
        executor=LocalExecutor(),
        acceptance=[
            AcceptanceCriterion(
                metric="overview/sps",
                threshold=15_000,
                metric_name="overview/sps [training compat 1.0]",
            )
        ],
        metrics={"overview/sps": 14_000.0},
    )

    assert _AcceptanceEvaluator()._passes_acceptance(job) is False
    assert job.acceptance_failures
    assert job.acceptance_failures[0].startswith("overview/sps [training compat 1.0]")
