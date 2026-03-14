"""Build Column scaffolds from explicit cell configs."""

from __future__ import annotations

from typing import Sequence

from pydantic import BaseModel

from cortex.cells import CellConfig as PublicCellConfig
from cortex.cells import default_cells
from cortex.config import (
    ColumnScaffoldConfig,
    RoutedAdapterConfig,
    RouterConfig,
    ScaffoldConfig,
)
from cortex.routed_adapter import apply_routed_adapter_
from cortex.scaffolds.column import ColumnScaffold
from cortex.scaffolds.registry import build_scaffold


def _clone_model(model: BaseModel) -> BaseModel:
    if hasattr(model, "model_copy"):
        return model.model_copy(deep=True)  # pydantic v2
    return model.copy(deep=True)  # pydantic v1


def _as_scaffold_config(cell: PublicCellConfig | ScaffoldConfig) -> ScaffoldConfig:
    if isinstance(cell, PublicCellConfig):
        return cell.as_scaffold_config()
    return _clone_model(cell)  # type: ignore[return-value]


def build_column_auto_config(
    *,
    d_hidden: int,
    cells: Sequence[PublicCellConfig | ScaffoldConfig] | None = None,
    router: RouterConfig | None = None,
) -> ColumnScaffoldConfig:
    del d_hidden
    configured_cells = list(cells) if cells is not None else default_cells()
    if not configured_cells:
        raise ValueError("cells produced no experts")

    experts = [_as_scaffold_config(cell) for cell in configured_cells]
    return ColumnScaffoldConfig(experts=experts, router=(router or RouterConfig()))


def build_column_auto_scaffold(
    *,
    d_hidden: int,
    cells: Sequence[PublicCellConfig | ScaffoldConfig] | None = None,
    router: RouterConfig | None = None,
    routed_adapter: RoutedAdapterConfig | None = None,
) -> ColumnScaffold:
    cfg = build_column_auto_config(d_hidden=d_hidden, cells=cells, router=router)
    scaffold = build_scaffold(config=cfg, d_hidden=d_hidden, core=None)  # type: ignore[arg-type]
    assert isinstance(scaffold, ColumnScaffold)
    if routed_adapter is not None and routed_adapter.enabled:
        apply_routed_adapter_(scaffold, routed_adapter)
    return scaffold


__all__ = ["build_column_auto_config", "build_column_auto_scaffold"]
