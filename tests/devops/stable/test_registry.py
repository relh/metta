from __future__ import annotations

import pytest

from devops.stable.stable_check_context import StableCheckContext
from devops.stable.stable_check_groups import StableCheckGroup
from devops.stable.stable_check_registry import discover_stable_checks, stable_check_configs_to_jobs
from devops.stable.stable_function_check_registry import StableFunctionCheckConfig, stable_function_check


def _names(specs) -> set[str]:  # noqa: ANN001
    return {config.name for config in specs}


def test_discover_jobs_filters_by_check_group() -> None:
    training_light_names = _names(discover_stable_checks({StableCheckGroup.INTERNAL_TRAINING_LIGHT}))
    training_heavy_names = _names(discover_stable_checks({StableCheckGroup.INTERNAL_TRAINING_HEAVY}))
    live_light_names = _names(discover_stable_checks({StableCheckGroup.LIVE_TESTS_LIGHT}))
    live_heavy_names = _names(discover_stable_checks({StableCheckGroup.LIVE_TESTS_HEAVY}))

    assert "ci.play_smoke" in training_light_names
    assert "arena_basic_easy_shaped.train_100m" not in training_light_names

    assert "arena_basic_easy_shaped.train_100m" in training_heavy_names
    assert "arena_basic_easy_shaped.train_2b" in training_heavy_names
    assert "ci.play_smoke" not in training_heavy_names

    # Live checks may be empty on infra-only branches, but must not include training checks.
    assert "ci.play_smoke" not in live_light_names
    assert "arena_basic_easy_shaped.train_100m" not in live_light_names
    assert "ci.play_smoke" not in live_heavy_names
    assert "arena_basic_easy_shaped.train_100m" not in live_heavy_names


def test_discover_jobs_unfiltered_contains_ci_and_prod_checks() -> None:
    names = _names(discover_stable_checks())
    assert "ci.play_smoke" in names
    assert "arena_basic_easy_shaped.train_100m" in names
    assert "arena_basic_easy_shaped.train_2b" in names


def test_specs_to_jobs_uses_function_check_adapter_for_stable_check() -> None:
    def install_cogames(ctx: StableCheckContext) -> None:
        _ = ctx
        return None

    install_cogames.__module__ = "devops.stable.function_checks.cogames_submission"
    check_configs = [
        StableFunctionCheckConfig(
            func=install_cogames,
            timeout_s=900,
            check_group=StableCheckGroup.LIVE_TESTS_LIGHT,
        )
    ]

    jobs = stable_check_configs_to_jobs(check_configs, prefix="test.stable")
    assert len(jobs) == 1
    assert jobs[0].cmd[:4] == ["uv", "run", "./tools/run.py", "devops.stable.stable_function_check_tool.run_check_tool"]
    assert jobs[0].cmd[4] == "check_path=devops.stable.function_checks.cogames_submission.install_cogames"


def test_specs_to_jobs_includes_lifecycle_metadata() -> None:
    check_configs = discover_stable_checks(check_groups={StableCheckGroup.INTERNAL_TRAINING_LIGHT})
    jobs = stable_check_configs_to_jobs(check_configs, prefix="test.stable")
    assert jobs
    assert all(job.metadata["lifecycle"] in {"active", "quarantined", "not_implemented"} for job in jobs)


def test_specs_to_jobs_wires_check_dependencies_and_input_references() -> None:
    def submit_policy_check(ctx: StableCheckContext) -> None:
        _ = ctx
        return None

    def verify_submission(ctx: StableCheckContext) -> None:
        _ = ctx
        return None

    submit_policy_check.__module__ = "devops.stable.function_checks.public_submission"
    verify_submission.__module__ = "devops.stable.function_checks.public_submission"

    check_configs = [
        StableFunctionCheckConfig(
            func=submit_policy_check,
            timeout_s=900,
            check_group=StableCheckGroup.LIVE_TESTS_LIGHT,
            output_references={"submission_ref_path": "devops/stable/state/{job_name}/submission_id.txt"},
        ),
        StableFunctionCheckConfig(
            func=verify_submission,
            timeout_s=900,
            check_group=StableCheckGroup.LIVE_TESTS_LIGHT,
            depends_on=submit_policy_check,
            input_references={"submission_ref_path": "submission_ref_path"},
        ),
    ]

    jobs = stable_check_configs_to_jobs(check_configs, prefix="test.stable")
    submit_job = next(job for job in jobs if job.name.endswith("public_submission.submit_policy_check"))
    verify_job = next(job for job in jobs if job.name.endswith("public_submission.verify_submission"))

    assert verify_job.dependencies == [submit_job.name]
    assert f"inputs.submission_ref_path=devops/stable/state/{submit_job.name}/submission_id.txt" in verify_job.cmd


def test_specs_to_jobs_raises_when_dependency_output_field_missing() -> None:
    def submit_policy_check(ctx: StableCheckContext) -> None:
        _ = ctx
        return None

    def verify_submission(ctx: StableCheckContext) -> None:
        _ = ctx
        return None

    submit_policy_check.__module__ = "devops.stable.function_checks.public_submission"
    verify_submission.__module__ = "devops.stable.function_checks.public_submission"

    check_configs = [
        StableFunctionCheckConfig(
            func=submit_policy_check,
            timeout_s=900,
            check_group=StableCheckGroup.LIVE_TESTS_LIGHT,
            output_references={"different_field": "foo"},
        ),
        StableFunctionCheckConfig(
            func=verify_submission,
            timeout_s=900,
            check_group=StableCheckGroup.LIVE_TESTS_LIGHT,
            depends_on=submit_policy_check,
            input_references={"submission_ref_path": "submission_ref_path"},
        ),
    ]

    with pytest.raises(ValueError, match="does not provide output field"):
        stable_check_configs_to_jobs(check_configs, prefix="test.stable")


def test_stable_check_requires_check_group() -> None:
    with pytest.raises(TypeError, match="check_group"):

        @stable_function_check(timeout_s=900)  # type: ignore[misc]
        def _invalid_check(ctx: StableCheckContext) -> None:
            _ = ctx
            return None


def test_stable_check_requires_single_context_argument() -> None:
    with pytest.raises(ValueError, match="StableCheckContext"):

        @stable_function_check(timeout_s=900, check_group=StableCheckGroup.LIVE_TESTS_LIGHT)
        def _invalid_check() -> None:
            return None
