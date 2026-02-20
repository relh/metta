from __future__ import annotations

from types import SimpleNamespace

import pytest

from devops.stable import stable_function_check_tool as check_tool
from devops.stable.stable_check_context import StableCheckContext
from devops.stable.stable_function_check_tool import StableFunctionCheckTool


def test_stable_function_check_tool_builds_context_and_passes_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def check_with_ctx(ctx: StableCheckContext) -> None:
        captured["job_name"] = ctx.job_name
        captured["submission_ref_path"] = ctx.inputs["submission_ref_path"]

    monkeypatch.setattr(
        check_tool.importlib,
        "import_module",
        lambda _name: SimpleNamespace(check_with_ctx=check_with_ctx),
    )

    tool = StableFunctionCheckTool(check_path="fake.module.check_with_ctx")
    tool.invoke(
        {
            "check_path": "fake.module.check_with_ctx",
            "job_name": "runner.stable.test",
            "submission_ref_path": "/tmp/submission.txt",
        }
    )

    assert captured["job_name"] == "runner.stable.test"
    assert captured["submission_ref_path"] == "/tmp/submission.txt"


def test_stable_function_check_tool_requires_job_name(monkeypatch: pytest.MonkeyPatch) -> None:
    def check_with_ctx(ctx: StableCheckContext) -> None:
        _ = ctx

    monkeypatch.setattr(
        check_tool.importlib,
        "import_module",
        lambda _name: SimpleNamespace(check_with_ctx=check_with_ctx),
    )

    tool = StableFunctionCheckTool(check_path="fake.module.check_with_ctx")

    with pytest.raises(ValueError, match="job_name"):
        tool.invoke({"check_path": "fake.module.check_with_ctx"})
