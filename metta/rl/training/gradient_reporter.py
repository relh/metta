"""Gradient statistics computation callback."""

import logging

import torch
import torch.nn.functional as F
from pydantic import Field
from tensordict import TensorDict
from torch import Tensor

from metta.rl.training import TrainerComponent
from mettagrid.base_config import Config

logger = logging.getLogger(__name__)


class GradientReporterConfig(Config):
    """Configuration for gradient statistics computation."""

    epoch_interval: int = Field(default=0, ge=0)
    """How often to compute gradient statistics (in epochs)."""


class GradientReporter(TrainerComponent):
    """Computes gradient statistics for monitoring."""

    def __init__(self, config: GradientReporterConfig):
        """Initialize gradient reporter component."""
        enabled = config.epoch_interval > 0
        super().__init__(epoch_interval=config.epoch_interval if enabled else 0)
        self._master_only = True
        self._enabled = enabled

    def on_epoch_end(self, epoch: int) -> None:
        """Compute gradient statistics for all trainable policies and stash on trainer."""
        if not self._enabled:
            return

        context = self.context
        policy_assets = context.policy_assets

        grad_stats = {}
        for policy_name, policy in policy_assets.policies.items():
            # Only process trainable policies
            if not policy_assets.get_config(policy_name).trainable:
                continue

            # Collect gradients for this policy
            gradients = [param.grad.view(-1) for param in policy.parameters() if param.grad is not None]
            if not gradients:
                continue

            # Compute statistics for this policy
            grad_tensor = torch.cat(gradients).to(torch.float32)
            grad_stats[f"grad/{policy_name}/mean"] = grad_tensor.mean().item()
            grad_stats[f"grad/{policy_name}/variance"] = grad_tensor.var().item()
            grad_stats[f"grad/{policy_name}/norm"] = grad_tensor.norm(2).item()

        if not grad_stats:
            return

        self.context.update_gradient_stats(grad_stats)

        stats_reporter = context.stats_reporter
        if stats_reporter and hasattr(stats_reporter, "update_grad_stats"):
            stats_reporter.update_grad_stats(grad_stats)


def analyze_loss_alignment(
    shared_data: TensorDict,
    name1: str,
    name2: str,
    params: list[Tensor],
    tracker: dict[str, list[float]],
) -> None:
    """
    Computes alignment metrics between two losses stored in shared_data.

    Args:
        shared_data: TensorDict containing the unreduced loss vectors.
                     Expects keys '{name1}_loss_vec' and '{name2}_loss_vec'
                     to contain *attached* tensors (part of the graph).
        name1: Name of the first loss (e.g. "ks_val").
        name2: Name of the second loss (e.g. "ppo_val").
        params: List of policy parameters to compute gradients for.
        tracker: Dictionary list to append metrics to.
    """
    key1 = f"{name1}_loss_vec"
    key2 = f"{name2}_loss_vec"

    if key1 not in shared_data or key2 not in shared_data:
        return

    # 1. Retrieve attached loss vectors
    loss_vec1 = shared_data[key1]
    loss_vec2 = shared_data[key2]

    # Flatten for comparison
    vec1_flat = loss_vec1.flatten()
    vec2_flat = loss_vec2.flatten()

    if vec1_flat.shape != vec2_flat.shape:
        return

    # 2. Vector-level metrics (detached)
    with torch.no_grad():
        # Cosine similarity of loss vectors (batch alignment)
        loss_cos = F.cosine_similarity(vec1_flat, vec2_flat, dim=0)
        tracker[f"{name1}_{name2}_loss_cos"].append(float(loss_cos.item()))

        # Variance of loss difference
        loss_diff_var = (vec1_flat - vec2_flat).var()
        tracker[f"{name1}_{name2}_loss_diff_var"].append(float(loss_diff_var.item()))

    # 3. Gradient-level metrics
    params_with_grad = [p for p in params if p.requires_grad]
    if not params_with_grad:
        return

    # Compute gradients of the scalar means
    loss_scalar1 = loss_vec1.mean()
    loss_scalar2 = loss_vec2.mean()

    # We must retain_graph because the graph is needed for the actual optimization step later
    # allow_unused=True is needed because some policy parameters (e.g. actor head)
    # might not be part of the value loss graph.
    grads1 = torch.autograd.grad(
        loss_scalar1, params_with_grad, retain_graph=True, create_graph=False, allow_unused=True
    )

    grads2 = torch.autograd.grad(
        loss_scalar2, params_with_grad, retain_graph=True, create_graph=False, allow_unused=True
    )

    # Flatten and concatenate, treating None as zeros
    def flatten_grads(grads, params):
        flat_list = []
        for g, p in zip(grads, params, strict=True):
            if g is None:
                flat_list.append(torch.zeros_like(p).flatten())
            else:
                flat_list.append(g.flatten())
        return torch.cat(flat_list)

    grad1_flat = flatten_grads(grads1, params_with_grad).detach()
    grad2_flat = flatten_grads(grads2, params_with_grad).detach()

    # Cosine similarity of gradients
    grad_cos = F.cosine_similarity(grad1_flat, grad2_flat, dim=0)
    tracker[f"{name1}_{name2}_grad_cos"].append(float(grad_cos.item()))

    # Variance of gradient differences
    grad_diff_var = (grad1_flat - grad2_flat).var()
    tracker[f"{name1}_{name2}_grad_diff_var"].append(float(grad_diff_var.item()))
