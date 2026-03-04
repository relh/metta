import importlib
import os

import pytest

from mettagrid.util.module import load_symbol


@pytest.fixture
def with_extra_imports_root(monkeypatch):
    """Add test fixtures to Python path for recipe/tool discovery."""
    extra_imports_root = os.path.join(os.path.dirname(__file__), "fixtures/extra-import-root")
    monkeypatch.setenv("PYTHONPATH", extra_imports_root)
    monkeypatch.syspath_prepend(extra_imports_root)


@pytest.mark.parametrize(
    ("symbol_name", "expected"),
    [
        ("builtins.str", str),
        ("importlib.import_module", importlib.import_module),
    ],
)
def test_load_symbol_with_builtin_or_stdlib(symbol_name: str, expected: object) -> None:
    assert load_symbol(symbol_name) is expected


def test_load_symbol_invalid_format_raises_value_error() -> None:
    with pytest.raises(ModuleNotFoundError) as excinfo:
        load_symbol("NotFullyQualifiedName")
    assert "Invalid symbol name" in str(excinfo.value)


def test_load_symbol_missing_module_raises_module_not_found_error() -> None:
    with pytest.raises(ModuleNotFoundError):
        load_symbol("this_module_does_not_exist__abcdef.Symbol")


def test_load_self() -> None:
    assert callable(load_symbol("mettagrid.util.module.load_symbol"))


@pytest.mark.parametrize(
    ("symbol_name", "expected_name"),
    [
        ("mettagrid.base_config.Config", "Config"),
        ("foo.bar.baz.Foo.Bar.Baz", "Baz"),
        ("notebook_fixture.NotebookPolicyClass", "NotebookPolicyClass"),
        ("notebook_fixture.NotebookPolicyClass.Config", "Config"),
    ],
)
def test_load_symbol_type_by_name(
    symbol_name: str,
    expected_name: str,
    with_extra_imports_root,
) -> None:
    result = load_symbol(symbol_name)
    assert isinstance(result, type)
    assert result.__name__ == expected_name
