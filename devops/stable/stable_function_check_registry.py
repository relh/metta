from __future__ import annotations

import importlib
import inspect
import pkgutil
import sys
from dataclasses import dataclass, field
from typing import Callable

from devops.datadog.models import VALID_CATEGORIES
from devops.runners.executors.local import LocalExecutor
from devops.runners.executors.skypilot import SkypilotExecutor
from devops.runners.job import Job
from devops.stable.stable_check_context import StableCheckContext
from devops.stable.stable_check_groups import StableCheckGroup
from devops.stable.stable_check_lifecycle import DEFAULT_LIFECYCLE, StableCheckLifecycle

FUNCTION_CHECK_TOOL_PATH = "devops.stable.stable_function_check_tool.run_check_tool"


@dataclass
class StableFunctionCheckConfig:
    """Configuration for a function-backed stable check."""

    func: Callable[[StableCheckContext], object]
    timeout_s: int

    check_group: StableCheckGroup = StableCheckGroup.LIVE_TESTS_LIGHT
    lifecycle: StableCheckLifecycle = DEFAULT_LIFECYCLE
    datadog_metric_category: str = "ci"

    depends_on: Callable[[StableCheckContext], object] | None = None
    input_references: dict[str, str] = field(default_factory=dict)
    output_references: dict[str, str] = field(default_factory=dict)

    remote_gpus: int | None = None
    remote_nodes: int | None = None

    @property
    def name(self) -> str:
        module = self.func.__module__
        short_module = (
            module.replace("devops.stable.function_checks.", "")
            .replace("recipes.prod.", "")
            .replace("recipes.experiment.", "")
        )
        return f"{short_module}.{self.func.__name__}"


_stable_function_check_registry: list[StableFunctionCheckConfig] = []


def stable_function_check(
    *,
    timeout_s: int,
    check_group: StableCheckGroup,
    lifecycle: StableCheckLifecycle = DEFAULT_LIFECYCLE,
    datadog_metric_category: str = "ci",
    depends_on: Callable[[StableCheckContext], object] | None = None,
    input_references: dict[str, str] | None = None,
    output_references: dict[str, str] | None = None,
    remote_gpus: int | None = None,
    remote_nodes: int | None = None,
) -> Callable[[Callable[[StableCheckContext], object]], Callable[[StableCheckContext], object]]:
    """Register a function-backed stable check."""

    def decorator(func: Callable[[StableCheckContext], object]) -> Callable[[StableCheckContext], object]:
        # Validate function signature.
        params = list(inspect.signature(func).parameters.values())
        if len(params) != 1 or params[0].kind not in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            raise ValueError(
                "stable_function_check functions must accept exactly one positional StableCheckContext argument"
            )

        # Validate config.
        if not isinstance(check_group, StableCheckGroup):
            raise TypeError(f"check_group must be StableCheckGroup, got {type(check_group).__name__}")
        if datadog_metric_category not in VALID_CATEGORIES:
            raise ValueError(
                f"Invalid datadog_metric_category '{datadog_metric_category}', "
                f"expected one of {sorted(VALID_CATEGORIES)}"
            )
        if (remote_gpus is not None) != (remote_nodes is not None):
            raise ValueError("remote checks must set both remote_gpus and remote_nodes")

        _stable_function_check_registry.append(
            StableFunctionCheckConfig(
                func=func,
                timeout_s=timeout_s,
                check_group=check_group,
                datadog_metric_category=datadog_metric_category,
                lifecycle=lifecycle,
                depends_on=depends_on,
                input_references=input_references or {},
                output_references=output_references or {},
                remote_gpus=remote_gpus,
                remote_nodes=remote_nodes,
            )
        )
        return func

    return decorator


def discover_stable_function_checks() -> list[StableFunctionCheckConfig]:
    """Discover registered function-backed stable checks."""
    import devops.stable.function_checks as function_checks_package  # noqa: PLC0415

    for module_info in pkgutil.walk_packages(function_checks_package.__path__, prefix="devops.stable.function_checks."):
        try:
            if module_info.name not in sys.modules:
                importlib.import_module(module_info.name)
        except Exception:
            pass

    return list(_stable_function_check_registry)


def _stable_function_check_config_to_job(
    config: StableFunctionCheckConfig,
    prefix: str,
    config_to_job_name: dict[Callable[[StableCheckContext], object], str],
    configs_by_func: dict[Callable[[StableCheckContext], object], StableFunctionCheckConfig],
) -> Job:
    check_path = f"{config.func.__module__}.{config.func.__name__}"
    job_name = f"{prefix}-{config.name}"
    dependencies: list[str] = []
    inject_args: list[str] = []

    if config.depends_on:
        dep_job_name = config_to_job_name.get(config.depends_on)
        if dep_job_name is None:
            raise ValueError(f"{config.name} depends_on target is not in discovered checks: {config.depends_on}")
        dependencies.append(dep_job_name)

        dep_config = configs_by_func.get(config.depends_on)
        if dep_config is None:
            raise ValueError(f"{config.name} depends_on target has no check config: {config.depends_on}")
        available_references = {
            key: value.format(job_name=dep_job_name) for key, value in dep_config.output_references.items()
        }
        for param_name, output_field in config.input_references.items():
            if output_field not in available_references:
                raise ValueError(f"Dependency {dep_job_name} does not provide output field: {output_field}")
            inject_args.append(f"inputs.{param_name}={available_references[output_field]}")

    if config.remote_gpus is not None:
        cmd = [
            "uv",
            "run",
            "./devops/skypilot/launch.py",
            FUNCTION_CHECK_TOOL_PATH,
            f"--gpus={config.remote_gpus}",
            f"--nodes={config.remote_nodes}",
            "--skip-git-check",
            f"check_path={check_path}",
        ]
        cmd.append(f"job_name={job_name}")
        cmd.extend(inject_args)
        executor = SkypilotExecutor()
    else:
        cmd = [
            "uv",
            "run",
            "./tools/run.py",
            FUNCTION_CHECK_TOOL_PATH,
            f"check_path={check_path}",
        ]
        cmd.append(f"job_name={job_name}")
        cmd.extend(inject_args)
        executor = LocalExecutor()

    return Job(
        name=job_name,
        cmd=cmd,
        executor=executor,
        timeout_s=config.timeout_s,
        remote_gpus=config.remote_gpus,
        remote_nodes=config.remote_nodes,
        dependencies=dependencies,
        metadata={
            "datadog_metric_category": config.datadog_metric_category,
            "check_group": config.check_group.value,
            "lifecycle": config.lifecycle.value,
        },
    )


def stable_function_check_configs_to_jobs(configs: list[StableFunctionCheckConfig], prefix: str) -> list[Job]:
    """Convert function check configs to runner jobs."""
    config_to_job_name: dict[Callable[[StableCheckContext], object], str] = {
        config.func: f"{prefix}-{config.name}" for config in configs
    }
    configs_by_func: dict[Callable[[StableCheckContext], object], StableFunctionCheckConfig] = {
        config.func: config for config in configs
    }
    return sorted(
        (
            _stable_function_check_config_to_job(config, prefix, config_to_job_name, configs_by_func)
            for config in configs
        ),
        key=lambda job: job.name,
    )
