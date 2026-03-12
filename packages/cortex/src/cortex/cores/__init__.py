"""Memory cell implementations for stateful neural computation."""

from cortex.cores.agalite import AGaLiTeCell
from cortex.cores.base import MemoryCell
from cortex.cores.conv import CausalConv1d
from cortex.cores.core import AxonCell, AxonLayer
from cortex.cores.hf_llama import HFLlamaLayerCell
from cortex.cores.lstm import LSTMCell
from cortex.cores.mlstm import mLSTMCell
from cortex.cores.registry import build_cell, get_cell_class, register_cell
from cortex.cores.slstm import sLSTMCell
from cortex.cores.xl import XLCell

MemoryCore = MemoryCell
AGaLiTeCore = AGaLiTeCell
AxonCore = AxonCell
CausalConv1dCore = CausalConv1d
HFLlamaLayerCore = HFLlamaLayerCell
LSTMCore = LSTMCell
mLSTMCore = mLSTMCell
sLSTMCore = sLSTMCell
XLCore = XLCell
build_core = build_cell
get_core_class = get_cell_class
register_core = register_cell

__all__ = [
    "MemoryCell",
    "MemoryCore",
    "CausalConv1d",
    "CausalConv1dCore",
    "LSTMCell",
    "LSTMCore",
    "mLSTMCell",
    "mLSTMCore",
    "AxonCell",
    "AxonCore",
    "AxonLayer",
    "sLSTMCell",
    "sLSTMCore",
    "XLCell",
    "XLCore",
    "HFLlamaLayerCell",
    "HFLlamaLayerCore",
    "AGaLiTeCell",
    "AGaLiTeCore",
    "register_cell",
    "register_core",
    "build_cell",
    "build_core",
    "get_cell_class",
    "get_core_class",
]
