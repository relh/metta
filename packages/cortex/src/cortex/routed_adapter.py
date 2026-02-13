"""Route-ID-routed adapter modules and stack-wide injection helpers."""

from __future__ import annotations

import contextlib
import contextvars
import math
from typing import Callable, Iterator, cast

import torch
import torch.nn as nn
import torch.nn.functional as F

from cortex.config import RoutedAdapterConfig

_ROUTE_IDS: contextvars.ContextVar[torch.Tensor | None] = contextvars.ContextVar("cortex_route_ids", default=None)


@contextlib.contextmanager
def use_route_ids(route_ids: torch.Tensor | None):
    token = _ROUTE_IDS.set(route_ids)
    try:
        yield
    finally:
        _ROUTE_IDS.reset(token)


def get_route_ids() -> torch.Tensor | None:
    return _ROUTE_IDS.get()


def _resolve_route_ids_for_batch(
    *,
    route_ids: torch.Tensor | None,
    batch_size: int,
    device: torch.device,
    num_slots: int,
    require_route_ids: bool,
) -> torch.Tensor:
    if route_ids is None:
        if require_route_ids:
            raise ValueError("Routed adapters are enabled; pass route_ids with shape [B] to CortexStack.forward/step.")
        return torch.zeros(batch_size, device=device, dtype=torch.long)

    if route_ids.dim() != 1:
        raise ValueError(f"route_ids must be 1D, got shape {tuple(route_ids.shape)}")

    ids = route_ids.to(device=device, dtype=torch.long)
    if bool((ids < 0).any()) or bool((ids >= num_slots).any()):
        raise ValueError(f"route_ids values must be in [0, {num_slots}), got min={ids.min()} max={ids.max()}")

    if ids.shape[0] != batch_size:
        raise ValueError(f"route_ids shape [{ids.shape[0]}] does not match required batch size {batch_size}.")
    return ids


def _infer_batch_dim(x: torch.Tensor, batch_size: int) -> int | None:
    if x.dim() < 2:
        return None
    candidates = [dim for dim in range(x.dim() - 1) if x.shape[dim] == batch_size]
    if not candidates:
        return None
    if 0 in candidates:
        return 0
    if len(candidates) == 1:
        return candidates[0]
    raise ValueError(f"Ambiguous batch dimension for shape {tuple(x.shape)} and batch size {batch_size}.")


def _repeat_factor_for_batch_dim(x: torch.Tensor, batch_dim: int) -> int:
    prefix_shape = tuple(x.shape[:-1])
    other_dims = prefix_shape[:batch_dim] + prefix_shape[batch_dim + 1 :]
    if not other_dims:
        return 1
    return int(math.prod(other_dims))


_ADAPTER_PARAM_NAMES = ("adapter_A", "adapter_B")


def _iter_trunk_params(module: nn.Module) -> Iterator[nn.Parameter]:
    seen: set[int] = set()
    for sub in module.modules():
        for name, param in sub.named_parameters(recurse=False):
            if id(param) in seen:
                continue
            seen.add(id(param))

            if not param.requires_grad:
                continue
            is_adapter_param = (
                isinstance(sub, (RoutedAdapterLinear, RoutedAdapterHeadwiseLinearExpand))
                and name in _ADAPTER_PARAM_NAMES
            )
            if is_adapter_param:
                continue

            yield param


def _ddp_keepalive(*params: nn.Parameter) -> torch.Tensor | None:
    """Attach params to the graph with zero weight for DDP gradient synchronization.

    To keep per-step overhead low, only touch a single element from each parameter
    instead of reducing the full tensor.
    """
    if not torch.is_grad_enabled():
        return None

    keepalive: torch.Tensor | None = None
    for param in params:
        if not param.requires_grad:
            continue
        first_index = (0,) * param.dim()
        term = param[first_index] * 0.0
        keepalive = term if keepalive is None else keepalive + term
    return keepalive


def _make_trunk_lr_mult_hook(param: nn.Parameter) -> Callable[[torch.Tensor], torch.Tensor]:
    def _hook(grad: torch.Tensor) -> torch.Tensor:
        mult = float(getattr(param, "_cortex_trunk_lr_mult", 1.0))
        if mult == 1.0:
            return grad
        return grad * mult

    return _hook


def set_trunk_lr_mult_(module: nn.Module, trunk_lr_mult: float) -> int:
    """Update the trunk gradient multiplier in-place.

    This affects all non-adapter parameters in ``module`` (i.e., excludes adapter A/B params).
    Call this before the backward pass for it to affect the current step.
    """
    mult = float(trunk_lr_mult)
    if mult < 0.0:
        raise ValueError(f"trunk_lr_mult must be >= 0, got {mult}")

    updated = 0
    for param in _iter_trunk_params(module):
        if not bool(getattr(param, "_cortex_trunk_lr_hooked", False)):
            param.register_hook(_make_trunk_lr_mult_hook(param))
            param._cortex_trunk_lr_hooked = True
        param._cortex_trunk_lr_mult = mult
        updated += 1
    return updated


class RoutedAdapterLinear(nn.Module):
    def __init__(
        self,
        in_features: int,
        out_features: int,
        *,
        bias: bool,
        num_slots: int,
        rank: int,
        alpha: float | None = None,
        dropout: float = 0.0,
        freeze_base: bool = False,
        require_route_ids: bool = True,
    ) -> None:
        super().__init__()
        self.in_features = int(in_features)
        self.out_features = int(out_features)
        self.num_slots = int(num_slots)
        self.rank = int(rank)
        self.alpha = float(alpha) if alpha is not None else float(rank)
        self.scale = self.alpha / float(max(1, self.rank))
        self.require_route_ids = bool(require_route_ids)

        self.weight = nn.Parameter(torch.empty(self.out_features, self.in_features))
        self.bias = nn.Parameter(torch.empty(self.out_features)) if bias else None

        self.adapter_A = nn.Parameter(torch.empty(self.num_slots, self.rank, self.in_features))
        self.adapter_B = nn.Parameter(torch.empty(self.num_slots, self.out_features, self.rank))
        self.dropout = nn.Dropout(float(dropout)) if float(dropout) > 0.0 else nn.Identity()

        self.reset_parameters()

        if freeze_base:
            self.weight.requires_grad_(False)
            if self.bias is not None:
                self.bias.requires_grad_(False)

    def reset_parameters(self) -> None:
        nn.init.kaiming_uniform_(self.weight, a=math.sqrt(5))
        if self.bias is not None:
            fan_in, _ = nn.init._calculate_fan_in_and_fan_out(self.weight)
            bound = 1 / math.sqrt(fan_in) if fan_in > 0 else 0
            nn.init.uniform_(self.bias, -bound, bound)
        nn.init.normal_(self.adapter_A, mean=0.0, std=1.0 / math.sqrt(max(1, self.rank)))
        nn.init.zeros_(self.adapter_B)

    @classmethod
    def from_linear(cls, linear: nn.Linear, cfg: RoutedAdapterConfig) -> RoutedAdapterLinear:
        module = cls(
            in_features=linear.in_features,
            out_features=linear.out_features,
            bias=linear.bias is not None,
            num_slots=cfg.num_slots,
            rank=cfg.rank,
            alpha=cfg.alpha,
            dropout=cfg.dropout,
            freeze_base=cfg.freeze_base,
            require_route_ids=cfg.require_route_ids,
        ).to(device=linear.weight.device, dtype=linear.weight.dtype)
        with torch.no_grad():
            module.weight.copy_(linear.weight)
            if linear.bias is not None and module.bias is not None:
                module.bias.copy_(linear.bias)
        return module

    def _resolve_route_ids(self, x: torch.Tensor) -> tuple[torch.Tensor, int] | None:
        route_ids = get_route_ids()
        if x.dim() < 2:
            if route_ids is None and self.require_route_ids:
                raise ValueError(
                    "Routed adapters are enabled; pass route_ids with shape [B] to CortexStack.forward/step."
                )
            return None

        if route_ids is None:
            if self.require_route_ids:
                raise ValueError(
                    "Routed adapters are enabled; pass route_ids with shape [B] to CortexStack.forward/step."
                )
            batch_dim = 0
            ids = _resolve_route_ids_for_batch(
                route_ids=None,
                batch_size=x.shape[batch_dim],
                device=x.device,
                num_slots=self.num_slots,
                require_route_ids=self.require_route_ids,
            )
            return ids, batch_dim

        if route_ids.dim() != 1:
            raise ValueError(f"route_ids must be 1D, got shape {tuple(route_ids.shape)}")
        ids_len = int(route_ids.shape[0])
        batch_dim = _infer_batch_dim(x, ids_len)
        if batch_dim is None:
            return None

        ids = _resolve_route_ids_for_batch(
            route_ids=route_ids,
            batch_size=x.shape[batch_dim],
            device=x.device,
            num_slots=self.num_slots,
            require_route_ids=self.require_route_ids,
        )
        return ids, batch_dim

    def _adapter_delta(self, x: torch.Tensor, ids: torch.Tensor, batch_dim: int) -> torch.Tensor:
        feature_dim = x.dim() - 1
        if batch_dim == 0:
            permuted = x
            inverse_prefix = list(range(feature_dim))
        else:
            perm = [batch_dim] + [dim for dim in range(feature_dim) if dim != batch_dim] + [feature_dim]
            permuted = x.permute(perm)
            ordered_prefix = [batch_dim] + [dim for dim in range(feature_dim) if dim != batch_dim]
            inverse_prefix = [ordered_prefix.index(dim) for dim in range(feature_dim)]

        batch_size = permuted.shape[0]
        repeat = _repeat_factor_for_batch_dim(permuted, 0)
        permuted_dropout = self.dropout(permuted)
        flat_x = permuted_dropout.reshape(batch_size * repeat, self.in_features)
        flat_ids = ids.repeat_interleave(repeat)

        A_sel = self.adapter_A.index_select(0, flat_ids)
        B_sel = self.adapter_B.index_select(0, flat_ids)
        tmp = torch.einsum("ni,nri->nr", flat_x, A_sel)
        delta_flat = torch.einsum("nr,nor->no", tmp, B_sel)

        delta_permuted = delta_flat.view(*permuted.shape[:-1], self.out_features)
        if batch_dim == 0:
            return delta_permuted
        return delta_permuted.permute(*inverse_prefix, feature_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        base = F.linear(x, self.weight, self.bias)
        keepalive = _ddp_keepalive(self.adapter_A, self.adapter_B)
        resolved = self._resolve_route_ids(x)
        if resolved is None:
            return base if keepalive is None else base + keepalive
        ids, batch_dim = resolved
        delta = self._adapter_delta(x, ids, batch_dim)
        out = base + delta * self.scale
        return out if keepalive is None else out + keepalive


class RoutedAdapterHeadwiseLinearExpand(nn.Module):
    def __init__(
        self,
        in_features: int,
        num_heads: int,
        *,
        bias: bool,
        num_slots: int,
        rank: int,
        alpha: float | None = None,
        dropout: float = 0.0,
        freeze_base: bool = False,
        require_route_ids: bool = True,
    ) -> None:
        super().__init__()
        if in_features % num_heads != 0:
            raise ValueError(f"in_features={in_features} must be divisible by num_heads={num_heads}")

        self.in_features = int(in_features)
        self.num_heads = int(num_heads)
        self.head_dim = self.in_features // self.num_heads
        self.num_slots = int(num_slots)
        self.rank = int(rank)
        self.alpha = float(alpha) if alpha is not None else float(rank)
        self.scale = self.alpha / float(max(1, self.rank))
        self.require_route_ids = bool(require_route_ids)

        self.weight = nn.Parameter(torch.empty(self.num_heads, self.head_dim, self.head_dim))
        self.bias = nn.Parameter(torch.empty(self.in_features)) if bias else None

        self.adapter_A = nn.Parameter(torch.empty(self.num_slots, self.num_heads, self.rank, self.head_dim))
        self.adapter_B = nn.Parameter(torch.empty(self.num_slots, self.num_heads, self.head_dim, self.rank))
        self.dropout = nn.Dropout(float(dropout)) if float(dropout) > 0.0 else nn.Identity()

        self.reset_parameters()

        if freeze_base:
            self.weight.requires_grad_(False)
            if self.bias is not None:
                self.bias.requires_grad_(False)

    def reset_parameters(self) -> None:
        std = (2.0 / (5.0 * self.head_dim)) ** 0.5
        nn.init.normal_(self.weight, mean=0.0, std=std)
        if self.bias is not None:
            nn.init.zeros_(self.bias)
        nn.init.normal_(self.adapter_A, mean=0.0, std=1.0 / math.sqrt(max(1, self.rank)))
        nn.init.zeros_(self.adapter_B)

    @classmethod
    def from_headwise_linear(cls, module: nn.Module, cfg: RoutedAdapterConfig) -> RoutedAdapterHeadwiseLinearExpand:
        if not all(hasattr(module, attr) for attr in ("num_heads", "weight", "head_dim")):
            raise ValueError("Expected a _HeadwiseLinearExpand-like module with num_heads/head_dim/weight attributes.")

        num_heads = int(cast(int, module.num_heads))  # type: ignore[attr-defined]
        head_dim = int(cast(int, module.head_dim))  # type: ignore[attr-defined]
        weight = cast(torch.Tensor, module.weight)  # type: ignore[attr-defined]
        bias_param = cast(torch.Tensor | None, module.bias if hasattr(module, "bias") else None)  # type: ignore[attr-defined]
        in_features = num_heads * head_dim
        out = cls(
            in_features=in_features,
            num_heads=num_heads,
            bias=bias_param is not None,
            num_slots=cfg.num_slots,
            rank=cfg.rank,
            alpha=cfg.alpha,
            dropout=cfg.dropout,
            freeze_base=cfg.freeze_base,
            require_route_ids=cfg.require_route_ids,
        ).to(device=weight.device, dtype=weight.dtype)
        with torch.no_grad():
            out.weight.copy_(weight)
            if bias_param is not None and out.bias is not None:
                out.bias.copy_(bias_param)
        return out

    def _resolve_route_ids(self, batch_size: int, *, device: torch.device) -> torch.Tensor:
        return _resolve_route_ids_for_batch(
            route_ids=get_route_ids(),
            batch_size=batch_size,
            device=device,
            num_slots=self.num_slots,
            require_route_ids=self.require_route_ids,
        )

    def _base_and_delta(self, xh: torch.Tensor, ids: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        A_sel = self.adapter_A.index_select(0, ids)
        B_sel = self.adapter_B.index_select(0, ids)
        xh_adapter = self.dropout(xh)
        if xh.dim() == 3:
            base = torch.einsum("bnd,ndf->bnf", xh, self.weight)
            tmp = torch.einsum("bnd,bnrd->bnr", xh_adapter, A_sel)
            delta = torch.einsum("bnr,bndr->bnd", tmp, B_sel)
            return base, delta

        base = torch.einsum("btnd,ndf->btnf", xh, self.weight)
        tmp = torch.einsum("btnd,bnrd->btnr", xh_adapter, A_sel)
        delta = torch.einsum("btnr,bndr->btnd", tmp, B_sel)
        return base, delta

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        keepalive = _ddp_keepalive(self.adapter_A, self.adapter_B)
        if x.dim() == 2:
            batch_size, hidden_size = x.shape
            xh = x.view(batch_size, self.num_heads, self.head_dim)
            ids = self._resolve_route_ids(batch_size=batch_size, device=x.device)
            base, delta = self._base_and_delta(xh, ids)
            y = (base + delta * self.scale).reshape(batch_size, hidden_size)
        elif x.dim() == 3:
            batch_size, seq_len, hidden_size = x.shape
            xh = x.view(batch_size, seq_len, self.num_heads, self.head_dim)
            ids = self._resolve_route_ids(batch_size=batch_size, device=x.device)
            base, delta = self._base_and_delta(xh, ids)
            y = (base + delta * self.scale).reshape(batch_size, seq_len, hidden_size)
        else:
            raise ValueError(f"RoutedAdapterHeadwiseLinearExpand expects x dim 2 or 3, got {x.dim()}")

        if self.bias is not None:
            y = y + self.bias
        return y if keepalive is None else y + keepalive


def _is_headwise_linear_expand(module: nn.Module) -> bool:
    return (
        module.__class__.__name__ == "_HeadwiseLinearExpand"
        and hasattr(module, "num_heads")
        and hasattr(module, "head_dim")
    )


def _apply_routed_adapter_replace_(module: nn.Module, cfg: RoutedAdapterConfig) -> int:
    replaced = 0
    for child_name, child in list(module.named_children()):
        if isinstance(child, RoutedAdapterLinear) or isinstance(child, RoutedAdapterHeadwiseLinearExpand):
            continue
        if isinstance(child, nn.Linear):
            setattr(module, child_name, RoutedAdapterLinear.from_linear(child, cfg))
            replaced += 1
            continue
        if _is_headwise_linear_expand(child):
            setattr(module, child_name, RoutedAdapterHeadwiseLinearExpand.from_headwise_linear(child, cfg))
            replaced += 1
            continue
        replaced += _apply_routed_adapter_replace_(child, cfg)
    return replaced


def apply_routed_adapter_(module: nn.Module, cfg: RoutedAdapterConfig) -> int:
    if not cfg.enabled:
        return 0

    replaced = _apply_routed_adapter_replace_(module, cfg)
    if cfg.trunk_lr_mult != 1.0:
        set_trunk_lr_mult_(module, cfg.trunk_lr_mult)
    return replaced


__all__ = [
    "RoutedAdapterLinear",
    "RoutedAdapterHeadwiseLinearExpand",
    "apply_routed_adapter_",
    "get_route_ids",
    "set_trunk_lr_mult_",
    "use_route_ids",
]
