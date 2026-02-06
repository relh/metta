"""Test fixture recipe with self-contained tool classes.

Uses lightweight Tool subclasses instead of real metta training infrastructure
to avoid transitive dependencies (e.g., metta.agent.components) that may not
be available in CI.
"""

from metta.common.tool import Tool


class EvaluateTool(Tool):
    """Mock evaluate tool for testing."""

    policy_uris: list[str] = []

    def invoke(self, args: dict[str, str]) -> int | None:
        print("EvaluateTool invoked")
        return 0


class TrainTool(Tool):
    """Mock train tool for testing."""

    def invoke(self, args: dict[str, str]) -> int | None:
        print("TrainTool invoked")
        return 0


def evaluate() -> EvaluateTool:
    """Explicit evaluate tool for testing."""
    return EvaluateTool(policy_uris=["mock://policy-uri"])


def train_shaped() -> TrainTool:
    """Explicit train tool for testing."""
    return TrainTool()
