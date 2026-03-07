"""Registry of scripted policy URIs derived from policy short_names."""

from __future__ import annotations

import ast
import functools
from pathlib import Path
from typing import Iterable, Optional

_POLICY_ROOT = Path(__file__).resolve().parent
_SCRIPTED_SCAN_DIRS = (
    _POLICY_ROOT / "scripted_agent",
    _POLICY_ROOT / "nim_agents",
)


def _iter_policy_files() -> Iterable[Path]:
    for base_dir in _SCRIPTED_SCAN_DIRS:
        if not base_dir.exists():
            continue
        for path in base_dir.rglob("*.py"):
            if path.name.startswith("__"):
                continue
            yield path


def _extract_literal_strings(node: ast.AST) -> Optional[list[str]]:
    if isinstance(node, (ast.List, ast.Tuple)):
        values: list[str] = []
        for elt in node.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                values.append(elt.value)
            else:
                return None
        return values
    return None


def _extract_short_names_from_class(class_def: ast.ClassDef) -> list[str]:
    for stmt in class_def.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name) and target.id == "short_names":
                    value = _extract_literal_strings(stmt.value)
                    return value or []
        if isinstance(stmt, ast.AnnAssign):
            if isinstance(stmt.target, ast.Name) and stmt.target.id == "short_names":
                if stmt.value is None:
                    return []
                value = _extract_literal_strings(stmt.value)
                return value or []
    return []


@functools.cache
def list_scripted_agent_names() -> tuple[str, ...]:
    names: set[str] = set()
    for path in _iter_policy_files():
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError:
            continue
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                names.update(_extract_short_names_from_class(node))
    return tuple(sorted(names))


SCRIPTED_AGENT_URIS: dict[str, str] = {name: f"metta://policy/{name}" for name in list_scripted_agent_names()}


def resolve_scripted_agent_uri(name: str) -> str:
    if name in SCRIPTED_AGENT_URIS:
        return SCRIPTED_AGENT_URIS[name]
    available = ", ".join(sorted(SCRIPTED_AGENT_URIS))
    raise ValueError(f"Unknown scripted agent '{name}'. Available: {available}")
