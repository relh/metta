from __future__ import annotations

import importlib
import pkgutil
import sys
from dataclasses import dataclass, field
from typing import Callable, get_type_hints

from devops.datadog.models import VALID_CATEGORIES
from devops.runners.acceptance_criterion import AcceptanceCriterion
from devops.runners.executors.local import LocalExecutor
from devops.runners.executors.skypilot import SkypilotExecutor
from devops.runners.job import Job
from devops.stable.stable_check_groups import StableCheckGroup
from devops.stable.stable_check_lifecycle import DEFAULT_LIFECYCLE, StableCheckLifecycle
from metta.common.tool import Tool
from metta.common.wandb.context import WandbConfig
from metta.tools.train import TrainTool


@dataclass
class StableToolCheckConfig:
    """Configuration for a tool-backed stable check."""

    func: Callable[..., Tool]
    timeout_s: int

    check_group: StableCheckGroup = StableCheckGroup.LIVE_TESTS_LIGHT
    lifecycle: StableCheckLifecycle = DEFAULT_LIFECYCLE
    datadog_metric_category: str = "ci"

    depends_on: Callable[..., Tool] | None = None
    input_references: dict[str, str] = field(default_factory=dict)

    remote_gpus: int | None = None
    remote_nodes: int | None = None

    acceptance: list[AcceptanceCriterion] = field(default_factory=list)

    @property
    def name(self) -> str:
        module = self.func.__module__
        short_module = module.replace("recipes.prod.", "").replace("recipes.experiment.", "")
        return f"{short_module}.{self.func.__name__}"


_stable_tool_check_registry: list[StableToolCheckConfig] = []


def stable_tool_check(
    *,
    depends_on: Callable[..., Tool] | None = None,
    input_references: dict[str, str] | None = None,
    timeout_s: int,
    remote_gpus: int | None = None,
    remote_nodes: int | None = None,
    acceptance: list[AcceptanceCriterion] | None = None,
    check_group: StableCheckGroup,
    datadog_metric_category: str = "ci",
    lifecycle: StableCheckLifecycle = DEFAULT_LIFECYCLE,
) -> Callable[[Callable[..., Tool]], Callable[..., Tool]]:
    """Register a tool-backed stable check."""

    def decorator(func: Callable[..., Tool]) -> Callable[..., Tool]:
        # Validate config.
        if not isinstance(check_group, StableCheckGroup):
            raise TypeError(f"check_group must be StableCheckGroup, got {type(check_group).__name__}")
        if datadog_metric_category not in VALID_CATEGORIES:
            raise ValueError(
                f"Invalid datadog_metric_category '{datadog_metric_category}', "
                f"expected one of {sorted(VALID_CATEGORIES)}"
            )

        _stable_tool_check_registry.append(
            StableToolCheckConfig(
                func=func,
                timeout_s=timeout_s,
                check_group=check_group,
                datadog_metric_category=datadog_metric_category,
                lifecycle=lifecycle,
                depends_on=depends_on,
                input_references=input_references or {},
                remote_gpus=remote_gpus,
                remote_nodes=remote_nodes,
                acceptance=acceptance or [],
            )
        )
        return func

    return decorator


def discover_stable_tool_checks() -> list[StableToolCheckConfig]:
    """Discover registered tool-backed stable checks."""
    import recipes.experiment as experiment_package  # noqa: PLC0415
    import recipes.prod as prod_package  # noqa: PLC0415

    packages_to_scan: list[tuple[object, str]] = [
        (prod_package, "recipes.prod."),
        (experiment_package, "recipes.experiment."),
    ]

    for package, module_prefix in packages_to_scan:
        for module_info in pkgutil.walk_packages(package.__path__, prefix=module_prefix):
            try:
                if module_info.name not in sys.modules:
                    importlib.import_module(module_info.name)
            except Exception:
                pass

    return list(_stable_tool_check_registry)


def stable_tool_check_configs_to_jobs(configs: list[StableToolCheckConfig], prefix: str) -> list[Job]:
    """Convert tool check configs to runner jobs."""
    jobs: list[Job] = []
    local_executor = LocalExecutor()
    skypilot_executor = SkypilotExecutor()

    config_to_job_name: dict[Callable, str] = {}
    for config in configs:
        config_to_job_name[config.func] = f"{prefix}-{config.name}"

    for config in configs:
        tool_path = f"{config.func.__module__}.{config.func.__name__}"
        job_name = config_to_job_name[config.func]

        return_type = get_type_hints(config.func).get("return")

        wandb_disabled = True
        if return_type is TrainTool:
            tool = config.func()
            assert isinstance(tool, TrainTool)
            wandb_disabled = not (tool.wandb.enabled or tool.wandb == WandbConfig.Unconfigured())

        if config.acceptance and wandb_disabled:
            raise ValueError(f"{config.name} must have wandb enabled to use acceptance criteria")

        assert (config.remote_gpus is not None) == (config.remote_nodes is not None), (
            "remote checks must have either gpus and nodes, or neither"
        )
        if config.remote_gpus:
            cmd = [
                "uv",
                "run",
                "./devops/skypilot/launch.py",
                tool_path,
                f"--gpus={config.remote_gpus}",
                f"--nodes={config.remote_nodes}",
                "--skip-git-check",
            ]
        else:
            cmd = ["uv", "run", "./tools/run.py", tool_path]
        if return_type is TrainTool:
            cmd.append(f"run={job_name}")

        dependencies: list[str] = []
        if config.depends_on and config.depends_on in config_to_job_name:
            dep_job_name = config_to_job_name[config.depends_on]
            dependencies.append(dep_job_name)

            inject_args = []
            available_references = config.depends_on().output_references(job_name=dep_job_name)
            for param_name, output_field in config.input_references.items():
                if output_field not in available_references:
                    raise ValueError(f"Dependency {dep_job_name} does not provide output field: {output_field}")
                value = available_references[output_field]
                inject_args.append(f"{param_name}={value}")
            cmd.extend(inject_args)

        executor = (
            skypilot_executor if config.remote_gpus is not None or config.remote_nodes is not None else local_executor
        )

        jobs.append(
            Job(
                name=job_name,
                cmd=cmd,
                executor=executor,
                timeout_s=config.timeout_s,
                remote_gpus=config.remote_gpus,
                remote_nodes=config.remote_nodes,
                dependencies=dependencies,
                wandb_run_name=job_name if not wandb_disabled else None,
                acceptance=config.acceptance,
                metadata={
                    "datadog_metric_category": config.datadog_metric_category,
                    "check_group": config.check_group.value,
                    "lifecycle": config.lifecycle.value,
                },
            )
        )

    return jobs
