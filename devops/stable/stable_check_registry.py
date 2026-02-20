from __future__ import annotations

from typing import Callable

from devops.runners.job import Job
from devops.stable.stable_check_groups import StableCheckGroup
from devops.stable.stable_function_check_registry import (
    StableFunctionCheckConfig,
    discover_stable_function_checks,
    stable_function_check_configs_to_jobs,
)
from devops.stable.stable_tool_check_registry import (
    StableToolCheckConfig,
    discover_stable_tool_checks,
    stable_tool_check_configs_to_jobs,
)

StableCheckConfig = StableToolCheckConfig | StableFunctionCheckConfig


def discover_stable_checks(check_groups: set[StableCheckGroup] | None = None) -> list[StableCheckConfig]:
    """Discover all tool-backed and function-backed checks."""
    tool_configs = discover_stable_tool_checks()
    function_configs = discover_stable_function_checks()

    all_configs_unsorted: list[StableCheckConfig] = [*tool_configs, *function_configs]
    all_configs = sorted(all_configs_unsorted, key=lambda config: config.name)

    if check_groups is None:
        return all_configs

    filtered_configs = [config for config in all_configs if config.check_group in check_groups]
    if len(filtered_configs) == 0:
        return []

    # If any included configs depend on other configs, need to include the dependencies too.
    configs_by_func: dict[Callable[..., object], StableCheckConfig] = {config.func: config for config in all_configs}
    visited_configs: dict[str, StableCheckConfig] = {}
    pending_configs_to_visit: list[StableCheckConfig] = list(filtered_configs)
    while len(pending_configs_to_visit) > 0:
        config = pending_configs_to_visit.pop()
        if config.name in visited_configs:
            continue
        visited_configs[config.name] = config
        depends_on = config.depends_on
        if depends_on is None:
            continue
        depended_on_config = configs_by_func[depends_on]
        if depended_on_config.name not in visited_configs:
            pending_configs_to_visit.append(depended_on_config)

    return sorted(visited_configs.values(), key=lambda config: config.name)


def stable_check_configs_to_jobs(configs: list[StableCheckConfig], prefix: str) -> list[Job]:
    """Convert tool-backed and function-backed stable check configs into runner jobs."""
    tool_configs = [config for config in configs if isinstance(config, StableToolCheckConfig)]
    function_configs = [config for config in configs if isinstance(config, StableFunctionCheckConfig)]

    tool_jobs = stable_tool_check_configs_to_jobs(tool_configs, prefix)
    function_jobs = stable_function_check_configs_to_jobs(function_configs, prefix)

    all_jobs_unsorted: list[Job] = [*tool_jobs, *function_jobs]
    return sorted(all_jobs_unsorted, key=lambda job: job.name)
