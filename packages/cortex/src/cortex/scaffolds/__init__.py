"""Scaffold components for composable memory cells."""

from cortex.scaffolds.adapter import AdapterScaffold
from cortex.scaffolds.base import BaseScaffold
from cortex.scaffolds.column import ColumnScaffold
from cortex.scaffolds.column.auto import build_column_auto_config, build_column_auto_scaffold
from cortex.scaffolds.passthrough import PassThroughScaffold
from cortex.scaffolds.postup import PostUpScaffold
from cortex.scaffolds.postup_gated import PostUpGatedScaffold
from cortex.scaffolds.preup import PreUpScaffold
from cortex.scaffolds.preup_gated import PreUpGatedScaffold
from cortex.scaffolds.registry import build_scaffold, get_scaffold_class, register_scaffold

__all__ = [
    "BaseScaffold",
    "AdapterScaffold",
    "PassThroughScaffold",
    "PreUpScaffold",
    "PreUpGatedScaffold",
    "PostUpScaffold",
    "PostUpGatedScaffold",
    "ColumnScaffold",
    "build_column_auto_config",
    "build_column_auto_scaffold",
    "register_scaffold",
    "build_scaffold",
    "get_scaffold_class",
]
