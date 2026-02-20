from __future__ import annotations

from enum import Enum


class StableCheckLifecycle(str, Enum):
    ACTIVE = "active"
    QUARANTINED = "quarantined"
    NOT_IMPLEMENTED = "not_implemented"


DEFAULT_LIFECYCLE = StableCheckLifecycle.ACTIVE
NON_BLOCKING_LIFECYCLES = frozenset({StableCheckLifecycle.QUARANTINED, StableCheckLifecycle.NOT_IMPLEMENTED})
