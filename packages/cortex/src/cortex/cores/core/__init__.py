"""Core Axon-based primitives.

This subpackage hosts the AxonCore (streaming RTU core) and AxonLayer, a
stateful, linear-like module that wraps AxonCore with automatic state
management.
"""

from .axon_core import AxonCore
from .axon_layer import AxonLayer, update_parent_state

__all__ = ["AxonCore", "AxonLayer", "update_parent_state"]
