"""Block components for composable memory cells."""

from cortex.scaffolds.adapter import AdapterBlock
from cortex.scaffolds.base import BaseBlock
from cortex.scaffolds.column import ColumnBlock
from cortex.scaffolds.column.auto import build_column_auto_block, build_column_auto_config
from cortex.scaffolds.passthrough import PassThroughBlock
from cortex.scaffolds.postup import PostUpBlock
from cortex.scaffolds.postup_gated import PostUpGatedBlock
from cortex.scaffolds.preup import PreUpBlock
from cortex.scaffolds.preup_gated import PreUpGatedBlock
from cortex.scaffolds.registry import build_block, get_block_class, register_block

AdapterScaffold = AdapterBlock
BaseScaffold = BaseBlock
ColumnScaffold = ColumnBlock
PassThroughScaffold = PassThroughBlock
PostUpScaffold = PostUpBlock
PostUpGatedScaffold = PostUpGatedBlock
PreUpScaffold = PreUpBlock
PreUpGatedScaffold = PreUpGatedBlock
build_scaffold = build_block
get_scaffold_class = get_block_class
register_scaffold = register_block

__all__ = [
    "BaseBlock",
    "BaseScaffold",
    "AdapterBlock",
    "AdapterScaffold",
    "PassThroughBlock",
    "PassThroughScaffold",
    "PreUpBlock",
    "PreUpScaffold",
    "PreUpGatedBlock",
    "PreUpGatedScaffold",
    "PostUpBlock",
    "PostUpScaffold",
    "PostUpGatedBlock",
    "PostUpGatedScaffold",
    "ColumnBlock",
    "ColumnScaffold",
    "build_column_auto_config",
    "build_column_auto_block",
    "register_block",
    "register_scaffold",
    "build_block",
    "build_scaffold",
    "get_block_class",
    "get_scaffold_class",
]
