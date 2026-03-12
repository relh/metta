"""Auto builder: stacks of Column layers built from explicit cell lists."""

from __future__ import annotations

from typing import Iterable, List, Sequence, cast

from pydantic import BaseModel

from cortex.cells import CellConfig as PublicCellConfig
from cortex.cells import default_cells
from cortex.config import CortexStackConfig, RoutedAdapterConfig, RouterConfig, ScaffoldConfig
from cortex.scaffolds.column.auto import build_column_auto_config
from cortex.stacks.base import CortexStack


def build_cortex_auto_config(
    *,
    d_hidden: int,
    num_layers: int = 2,
    layers: Sequence[Sequence[PublicCellConfig | ScaffoldConfig]] | None = None,
    router: RouterConfig | None = None,
    post_norm: bool = True,
    compile_blocks: bool = True,
    override_global_configs: Iterable[BaseModel] | None = None,
    routed_adapter: RoutedAdapterConfig | None = None,
) -> CortexStackConfig:
    """Build a CortexStackConfig with Column layers from explicit cell lists."""

    configured_layers = _resolve_layers(num_layers=num_layers, layers=layers)

    blocks: list[ScaffoldConfig] = []
    for layer_cells in configured_layers:
        col_cfg = build_column_auto_config(d_hidden=d_hidden, cells=layer_cells, router=router)
        blocks.append(col_cfg)

    if override_global_configs:
        blocks = [cast(ScaffoldConfig, _apply_overrides_model(block, override_global_configs)) for block in blocks]

    return CortexStackConfig(
        blocks=blocks,
        d_hidden=d_hidden,
        post_norm=post_norm,
        compile_blocks=bool(compile_blocks),
        routed_adapter=routed_adapter,
    )


def build_cortex_auto_stack(
    *,
    d_hidden: int,
    num_layers: int = 4,
    layers: Sequence[Sequence[PublicCellConfig | ScaffoldConfig]] | None = None,
    router: RouterConfig | None = None,
    post_norm: bool = True,
    compile_blocks: bool = True,
    override_global_configs: Iterable[BaseModel] | None = None,
    routed_adapter: RoutedAdapterConfig | None = None,
) -> CortexStack:
    """Build a Column-based CortexStack with per-layer cells."""

    cfg = build_cortex_auto_config(
        d_hidden=d_hidden,
        num_layers=num_layers,
        layers=layers,
        router=router,
        post_norm=post_norm,
        compile_blocks=compile_blocks,
        override_global_configs=override_global_configs,
        routed_adapter=routed_adapter,
    )
    return CortexStack(cfg)


def _resolve_layers(
    *,
    num_layers: int,
    layers: Sequence[Sequence[PublicCellConfig | ScaffoldConfig]] | None,
) -> list[list[PublicCellConfig | ScaffoldConfig]]:
    if layers is not None:
        configured_layers = [list(layer) for layer in layers]
        if not configured_layers:
            raise ValueError("layers produced no Column scaffolds")
        return configured_layers
    return [[cast(PublicCellConfig, _clone_model(cell)) for cell in default_cells()] for _ in range(num_layers)]


def _clone_model(model: BaseModel) -> BaseModel:
    if hasattr(model, "model_copy"):
        return model.model_copy(deep=True)  # pydantic v2
    return model.copy(deep=True)  # pydantic v1


def _merge_model(model: BaseModel, update: BaseModel) -> BaseModel:
    """Return a new model with explicitly set fields from update overriding model."""
    fields_set = getattr(update, "model_fields_set", None) or getattr(update, "__fields_set__", None)
    if hasattr(model, "model_copy") and hasattr(update, "model_dump"):
        if fields_set:
            dump_all = update.model_dump()
            upd = {k: dump_all[k] for k in fields_set if k in dump_all}
        else:
            upd = update.model_dump(exclude_unset=True)
        return model.model_copy(update=upd)  # type: ignore[attr-defined]
    upd_data = update.dict()
    if fields_set:
        upd = {k: upd_data[k] for k in fields_set if k in upd_data}
    else:
        upd = update.dict(exclude_unset=True)
    data = model.dict()
    data.update(upd)
    return type(model)(**data)


def _apply_overrides_model(model: BaseModel, overrides: Iterable[BaseModel]) -> BaseModel:
    for override in overrides:
        if isinstance(model, type(override)):
            return _merge_model(model, override)

    cloned = _clone_model(model)
    fields = getattr(cloned, "model_fields", None) or getattr(cloned, "__fields__", {})
    for name in fields:
        value = getattr(cloned, name, None)
        new_value = _apply_overrides_value(value, overrides)
        if new_value is not value:
            setattr(cloned, name, new_value)
    return cloned


def _apply_overrides_value(value, overrides: Iterable[BaseModel]):
    if isinstance(value, BaseModel):
        return _apply_overrides_model(value, overrides)
    if isinstance(value, list):
        changed = False
        out: List = []
        for item in value:
            new_item = _apply_overrides_value(item, overrides)
            changed = changed or (new_item is not item)
            out.append(new_item)
        return out if changed else value
    return value
