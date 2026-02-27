"""Utility functions for agent operations."""

import numpy as np
import torch
from tensordict import TensorDict
from torch import Tensor

_POLICY_METADATA_CACHE: dict[tuple[str, int, int], tuple[Tensor, Tensor]] = {}


def _get_policy_metadata_tensors(
    device: torch.device,
    batch_size: int,
    time_steps: int,
    cache: dict[tuple[str, int, int], tuple[Tensor, Tensor]] | None = None,
) -> tuple[Tensor, Tensor]:
    if cache is None:
        cache = _POLICY_METADATA_CACHE
    key = (str(device), batch_size, time_steps)
    cached = cache.get(key)
    if cached is None or cached[0].device != device:
        total = batch_size * time_steps
        cached = (
            torch.full((total,), batch_size, dtype=torch.long, device=device),
            torch.full((total,), time_steps, dtype=torch.long, device=device),
        )
        cache[key] = cached
    return cached


def ensure_sequence_metadata(
    td: TensorDict,
    *,
    batch_size: int,
    time_steps: int,
    cache: dict[tuple[str, int, int], tuple[Tensor, Tensor]] | None = None,
) -> None:
    keys = td.keys()
    needs_batch = "batch" not in keys
    needs_bptt = "bptt" not in keys
    if not (needs_batch or needs_bptt):
        return
    device = td.device
    if device is None:
        for key in td.keys():
            val = td[key]
            if isinstance(val, Tensor):
                device = val.device
                break
    if device is None:
        raise ValueError("TensorDict has no device and contains no tensors to infer device from")
    batch_tensor, bptt_tensor = _get_policy_metadata_tensors(device, batch_size, time_steps, cache=cache)
    if needs_batch:
        td.set("batch", batch_tensor)
    if needs_bptt:
        td.set("bptt", bptt_tensor)


def obs_to_td(obs: np.ndarray, device: str | torch.device = "cpu") -> TensorDict:
    """Convert numpy observations to TensorDict with standard metadata for policy inference."""

    env_obs = torch.from_numpy(obs).to(device)
    batch_size = env_obs.shape[0]
    td = TensorDict({"env_obs": env_obs}, batch_size=(batch_size,))
    ensure_sequence_metadata(td, batch_size=batch_size, time_steps=1)
    return td


def resolve_torch_dtype(dtype_str: str | None) -> torch.dtype:
    """Resolve common dtype strings to torch dtypes with float32 default."""
    if dtype_str is None:
        return torch.float32
    s = str(dtype_str).lower()
    return {"float16": torch.float16, "fp16": torch.float16, "bfloat16": torch.bfloat16, "bf16": torch.bfloat16}.get(
        s, torch.float32
    )
