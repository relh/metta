from typing import Literal

from pydantic import Field

from metta.common.tool import Tool
from mettagrid.base_config import Config


class NestedConfig(Config):
    """A nested configuration object for testing."""

    field: str = "nested_default"
    another_field: int = 100


DEFAULT_SETTINGS = NestedConfig()


class TestTool(Tool):
    def invoke(self, args):
        print("TestTool invoked")
        return 0


class SimpleTestTool(Tool):
    """A simple tool with a field for testing."""

    value: str = "default"
    nested: NestedConfig = Field(default_factory=NestedConfig)

    def invoke(self, args: dict[str, str]) -> int | None:
        print(f"Args: {args}")
        print(f"Tool value: {self.value}")
        print(f"Tool nested.field: {self.nested.field}")
        print(f"Tool nested.another_field: {self.nested.another_field}")
        return 0


def make_test_tool(
    run: str = "default_run",
    count: int = 42,
    settings: NestedConfig = DEFAULT_SETTINGS,
) -> SimpleTestTool:
    """Function that creates a test tool."""
    return SimpleTestTool(nested=settings.model_copy(deep=True))


class RequiredFieldTool(Tool):
    """Tool with a required field (no default). Used to verify constructor validation."""

    x: int

    def invoke(self, args: dict[str, str]) -> int | None:
        # Print the value so tests can assert behavior via subprocess output
        print(self.x)
        return 0


class EffectiveConfigTool(Tool):
    """Tool used to validate --print-effective-config behavior."""

    x: int = 1

    def apply_defaults_and_mutations(self, args: dict[str, str]) -> None:
        _ = args
        self.x = 2

    def invoke(self, args: dict[str, str]) -> int | None:
        print(f"x={self.x}")
        return 0


class LiteralNoneTool(Tool):
    """Tool for regression testing string literal 'none' overrides."""

    render: Literal["gui", "none"] = "gui"

    def invoke(self, args: dict[str, str]) -> int | None:
        _ = args
        print(f"render={self.render}")
        return 0
