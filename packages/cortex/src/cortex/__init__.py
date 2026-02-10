"""Cortex: Modular neural stack library for stateful memory cells and composable blocks."""

from cortex.blocks import (
    AdapterBlock,
    BaseBlock,
    ColumnBlock,
    PassThroughBlock,
    PostUpBlock,
    PreUpBlock,
    build_block,
    build_column_auto_block,
    build_column_auto_config,
    register_block,
)
from cortex.cells import (
    AxonCell,
    AxonLayer,
    CausalConv1d,
    LSTMCell,
    MemoryCell,
    build_cell,
    mLSTMCell,
    register_cell,
    sLSTMCell,
)
from cortex.config import (
    AdapterBlockConfig,
    AxonConfig,
    BlockConfig,
    CausalConv1dConfig,
    CellConfig,
    ColumnBlockConfig,
    CortexStackConfig,
    LSTMCellConfig,
    PassThroughBlockConfig,
    PostUpBlockConfig,
    PreUpBlockConfig,
    RoutedAdapterConfig,
    RouterConfig,
    XLCellConfig,
    mLSTMCellConfig,
    sLSTMCellConfig,
)
from cortex.consistent_dropout import (
    ConsistentDropout,
    ConsistentDropoutModule,
    reset_consistent_dropout,
)
from cortex.factory import build_cortex, build_from_dict
from cortex.routed_adapter import (
    RoutedAdapterHeadwiseLinearExpand,
    RoutedAdapterLinear,
    apply_routed_adapter_,
    get_route_ids,
    set_trunk_lr_mult_,
    use_route_ids,
)
from cortex.stacks import CortexStack
from cortex.types import MaybeState, ResetMask, State, Tensor
from cortex.utils import TRITON_AVAILABLE, select_backend

__all__ = [
    # Configuration
    "BlockConfig",
    "AdapterBlockConfig",
    "RoutedAdapterConfig",
    "ColumnBlockConfig",
    "PassThroughBlockConfig",
    "PreUpBlockConfig",
    "PostUpBlockConfig",
    "RouterConfig",
    "CortexStackConfig",
    "CellConfig",
    "AxonConfig",
    "CausalConv1dConfig",
    "LSTMCellConfig",
    "XLCellConfig",
    "mLSTMCellConfig",
    "sLSTMCellConfig",
    # Main classes
    "CortexStack",
    # Cells
    "MemoryCell",
    "AxonCell",
    "AxonLayer",
    "CausalConv1d",
    "LSTMCell",
    "mLSTMCell",
    "sLSTMCell",
    "register_cell",
    "build_cell",
    # Blocks
    "BaseBlock",
    "AdapterBlock",
    "ColumnBlock",
    "build_column_auto_config",
    "build_column_auto_block",
    "PassThroughBlock",
    "PreUpBlock",
    "PostUpBlock",
    "register_block",
    "build_block",
    # Routed adapters
    "RoutedAdapterLinear",
    "RoutedAdapterHeadwiseLinearExpand",
    "apply_routed_adapter_",
    "get_route_ids",
    "set_trunk_lr_mult_",
    "use_route_ids",
    # Types
    "MaybeState",
    "ResetMask",
    "State",
    "Tensor",
    # Factory functions
    "build_cortex",
    "build_from_dict",
    # Utils
    "TRITON_AVAILABLE",
    "select_backend",
    # Dropout
    "ConsistentDropout",
    "ConsistentDropoutModule",
    "reset_consistent_dropout",
]
