from __future__ import annotations

import importlib

from pydantic import Field

from devops.stable.stable_check_context import StableCheckContext
from metta.common.tool import Tool


class StableFunctionCheckTool(Tool):
    """Tool adapter that executes a function check by dotted path."""

    check_path: str
    job_name: str = ""
    inputs: dict[str, str] = Field(default_factory=dict)

    def invoke(self, args: dict[str, str]) -> int:
        module_name, _, func_name = self.check_path.rpartition(".")
        if not module_name or not func_name:
            raise ValueError(f"Invalid check path: {self.check_path}")

        module = importlib.import_module(module_name)
        func = getattr(module, func_name)
        if not callable(func):
            raise TypeError(f"Check path {self.check_path} does not resolve to a callable")

        raw_job_name = self.job_name or args.get("job_name", "")
        job_name = raw_job_name if isinstance(raw_job_name, str) else str(raw_job_name)
        if not job_name:
            raise ValueError("Stable function checks require non-empty `job_name` input")

        payload: dict[str, str] = dict(self.inputs)
        arg_inputs = args.get("inputs")
        if isinstance(arg_inputs, dict):
            payload.update({str(key): str(value) for key, value in arg_inputs.items()})
        for key, value in args.items():
            if key in {"check_path", "job_name", "inputs"}:
                continue
            if key.startswith("inputs."):
                payload[key.removeprefix("inputs.")] = str(value)
                continue
            # Backward-compatible shorthand for direct invocation in tests/scripts.
            payload[key] = str(value)

        ctx = StableCheckContext(job_name=job_name, inputs=payload)
        func(ctx)
        return 0


def run_check_tool(check_path: str) -> StableFunctionCheckTool:
    return StableFunctionCheckTool(check_path=check_path)
