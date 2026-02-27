"""CUDA teacher registry and runner.

CUDA teacher policies run in the trainer process on GPU, replacing the
env-side supervisor path for scripted teachers.  Each implementation
registers itself via the ``@register_cuda_teacher`` decorator.
"""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

import torch

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_CUDA_TEACHER_REGISTRY: dict[str, type] = {}


def register_cuda_teacher(name: str):
    """Class decorator that registers a CUDA teacher implementation.

    The decorated class must implement::

        __init__(self, policy_env_info: PolicyEnvInterface, device: torch.device)
        step_batch(self, observations: torch.Tensor, actions: torch.Tensor, dones: torch.Tensor | None = None) -> None
    """

    def decorator(cls):
        if name in _CUDA_TEACHER_REGISTRY:
            existing = _CUDA_TEACHER_REGISTRY[name]
            if existing is not cls:
                raise ValueError(
                    f"CUDA teacher '{name}' already registered to {existing.__module__}.{existing.__qualname__}"
                )
        _CUDA_TEACHER_REGISTRY[name] = cls
        return cls

    return decorator


def _discover_cuda_teachers() -> None:
    """Import all sibling submodules to trigger @register_cuda_teacher decorators."""
    package_dir = Path(__file__).parent
    package_name = __name__  # "metta.rl.training.cuda_teacher"
    for info in pkgutil.iter_modules([str(package_dir)]):
        if info.name.startswith("_"):
            continue
        importlib.import_module(f"{package_name}.{info.name}")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class CudaTeacherRunner:
    """Runs a CUDA scripted teacher in the trainer process."""

    def __init__(self, policy_uri: str, device: torch.device, policy_env_info) -> None:
        self.device = device

        # Extract the short name from the URI
        # e.g. "metta://policy/thinky" → "thinky"
        short_name = policy_uri.rstrip("/").split("/")[-1]
        # Strip query params: "thinky?miner=4" → "thinky"
        short_name = short_name.split("?")[0]

        _discover_cuda_teachers()

        if short_name not in _CUDA_TEACHER_REGISTRY:
            available = ", ".join(sorted(_CUDA_TEACHER_REGISTRY)) or "(none)"
            raise ValueError(f"No CUDA teacher registered for '{short_name}'. Available: {available}")

        self._policy = _CUDA_TEACHER_REGISTRY[short_name](policy_env_info, device)

    def step_batch(
        self,
        observations: torch.Tensor,
        actions: torch.Tensor,
        dones: torch.Tensor | None = None,
    ) -> None:
        """Compute teacher actions for all agents, in-place.

        Args:
            observations: ``[N, num_tokens, token_dim]`` uint8 tensor on GPU.
            actions: ``[N]`` int64 tensor on GPU, filled in-place.
            dones: ``[N]`` bool tensor on GPU, optional. Resets agent state on episode boundaries.
        """
        self._policy.step_batch(observations, actions, dones)
