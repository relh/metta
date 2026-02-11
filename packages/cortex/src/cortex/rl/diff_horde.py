from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import torch
from tensordict import TensorDict
from torch import Tensor

from cortex.kernels.pytorch import discounted_sum_pytorch
from cortex.utils import select_backend


def _as_vector_param(param: float | Tensor, *, size: int, device: torch.device, dtype: torch.dtype) -> Tensor:
    if isinstance(param, Tensor):
        param_tensor = param
    else:
        param_tensor = torch.tensor(param, device=device, dtype=dtype)

    param_tensor = param_tensor.to(device=device, dtype=dtype)
    if param_tensor.dim() == 0:
        return param_tensor.expand(size)
    if param_tensor.dim() == 1 and param_tensor.shape[0] == size:
        return param_tensor
    raise ValueError(f"Expected scalar or shape [{size}], got {tuple(param_tensor.shape)}")


def gather_action_values(values_btAF: Tensor, actions_bt: Tensor) -> Tensor:
    """Gather `[B,T,A,F]` values at `actions_bt` into `[B,T,F]`."""
    if values_btAF.dim() != 4:
        raise ValueError(f"Expected values with shape [B,T,A,F], got {tuple(values_btAF.shape)}")
    if actions_bt.dim() != 2:
        raise ValueError(f"Expected actions with shape [B,T], got {tuple(actions_bt.shape)}")

    actions_long = actions_bt.to(dtype=torch.int64)
    index = actions_long.unsqueeze(-1).unsqueeze(-1).expand(*actions_long.shape, 1, values_btAF.shape[-1])
    return values_btAF.gather(dim=2, index=index).squeeze(2)


def reverse_discounted_sum(x_btD: Tensor, discounts_btD: Tensor) -> Tensor:
    """
    Compute `y_t = x_t + discounts_t * y_{t+1}` over time dimension `T`, with `y_{T-1}=x_{T-1}`.

    This is equivalent to a forward discounted sum on the reversed sequence with `start_state=0`.
    """
    if x_btD.shape != discounts_btD.shape:
        raise ValueError(
            f"x and discounts must have the same shape, got {tuple(x_btD.shape)} vs {tuple(discounts_btD.shape)}"
        )
    if x_btD.dim() < 2:
        raise ValueError(f"Expected x with shape [B,T,...], got {tuple(x_btD.shape)}")
    if x_btD.shape[1] == 0:
        return x_btD

    x_rev_tbd = x_btD.flip(1).transpose(0, 1)
    discounts_rev_tbd = discounts_btD.flip(1).transpose(0, 1)
    start_state = torch.zeros_like(x_rev_tbd[0])
    fn = select_backend(
        triton_fn=None,
        pytorch_fn=discounted_sum_pytorch,
        tensor=x_btD,
        allow_triton=False,
        cuda_fn="cortex.kernels.cuda.agalite.discounted_sum_cuda:discounted_sum_cuda",
        allow_cuda=True,
    )
    out_rev_tbd = fn(start_state, x_rev_tbd, discounts_rev_tbd)
    return out_rev_tbd.transpose(0, 1).flip(1)


def diff_horde_delta(
    *,
    psi_btF: Tensor,
    phi_btF: Tensor,
    phi_bar_btF: Tensor,
    resets_bt: Tensor,
    gamma: float | Tensor,
) -> Tensor:
    """One-step differential TD error for vector GVFs, shape `[B,T-1,F]`."""
    if psi_btF.shape != phi_btF.shape or psi_btF.shape != phi_bar_btF.shape:
        raise ValueError("psi_btF, phi_btF, and phi_bar_btF must have the same shape [B,T,F]")
    if psi_btF.dim() != 3:
        raise ValueError(f"Expected [B,T,F] tensors, got {tuple(psi_btF.shape)}")
    if resets_bt.shape != psi_btF.shape[:2]:
        raise ValueError(f"Expected resets_bt shape {tuple(psi_btF.shape[:2])}, got {tuple(resets_bt.shape)}")

    _, t, f = psi_btF.shape
    if t <= 1:
        return psi_btF[:, :0, :]

    gamma_f = _as_vector_param(gamma, size=f, device=psi_btF.device, dtype=psi_btF.dtype).view(1, 1, f)

    psi_t = psi_btF[:, :-1, :]
    psi_tp1 = psi_btF[:, 1:, :]
    phi_tp1 = phi_btF[:, 1:, :]
    phi_bar_tp1 = phi_bar_btF[:, 1:, :]
    mask_tp1 = (1.0 - resets_bt[:, 1:]).unsqueeze(-1)

    return (phi_tp1 - phi_bar_tp1) + mask_tp1 * gamma_f * psi_tp1 - psi_t


def diff_horde_forward_view_residual(
    *,
    delta_bt1F: Tensor,
    resets_bt: Tensor,
    gamma: float | Tensor,
    lambda_: float | Tensor,
    rho_bt: Tensor | None = None,
    rho_clip: float | None = None,
) -> tuple[Tensor, dict[str, Tensor]]:
    """Forward-view TD(λ) residual Δ, shape `[B,T-1,F]`, with optional per-decision IS."""
    if delta_bt1F.dim() != 3:
        raise ValueError(f"Expected delta_bt1F with shape [B,T-1,F], got {tuple(delta_bt1F.shape)}")
    b, t1, f = delta_bt1F.shape
    if resets_bt.shape[0] != b or resets_bt.shape[1] != t1 + 1:
        raise ValueError("Expected resets_bt with shape [B,T] matching delta_bt1F's [B,T-1]")

    gamma_f = _as_vector_param(gamma, size=f, device=delta_bt1F.device, dtype=delta_bt1F.dtype).view(1, 1, f)
    lambda_f = _as_vector_param(lambda_, size=f, device=delta_bt1F.device, dtype=delta_bt1F.dtype).view(1, 1, f)
    gamma_lambda_f = gamma_f * lambda_f

    mask_tp1 = (1.0 - resets_bt[:, 1:]).unsqueeze(-1)

    rho_t = None
    if rho_bt is not None:
        if rho_bt.shape != resets_bt.shape:
            raise ValueError(f"Expected rho_bt shape {tuple(resets_bt.shape)}, got {tuple(rho_bt.shape)}")
        rho_t = rho_bt[:, :-1].to(device=delta_bt1F.device, dtype=delta_bt1F.dtype).unsqueeze(-1)
        if rho_clip is not None:
            rho_t = rho_t.clamp(max=float(rho_clip))

    if rho_t is None:
        rho_t = torch.ones((b, t1, 1), device=delta_bt1F.device, dtype=delta_bt1F.dtype)

    x = rho_t * delta_bt1F
    discounts = rho_t * mask_tp1 * gamma_lambda_f
    delta_lambda = reverse_discounted_sum(x, discounts)

    metrics: dict[str, Tensor] = {
        "delta_lambda_abs_mean": delta_lambda.detach().abs().mean(),
    }
    if rho_bt is not None and rho_clip is not None:
        with torch.no_grad():
            rho_trim = rho_bt[:, :-1]
            metrics["rho_clipfrac"] = (rho_trim > float(rho_clip)).to(dtype=delta_bt1F.dtype).mean()

    return delta_lambda, metrics


def diff_horde_delta_lambda(
    *,
    psi_btF: Tensor,
    phi_btF: Tensor,
    phi_bar_btF: Tensor,
    resets_bt: Tensor,
    gamma: float | Tensor,
    lambda_: float | Tensor,
    rho_bt: Tensor | None = None,
    rho_clip: float | None = None,
) -> tuple[Tensor, dict[str, Tensor]]:
    delta = diff_horde_delta(
        psi_btF=psi_btF,
        phi_btF=phi_btF,
        phi_bar_btF=phi_bar_btF,
        resets_bt=resets_bt,
        gamma=gamma,
    )
    return diff_horde_forward_view_residual(
        delta_bt1F=delta,
        resets_bt=resets_bt,
        gamma=gamma,
        lambda_=lambda_,
        rho_bt=rho_bt,
        rho_clip=rho_clip,
    )


@dataclass(frozen=True, slots=True)
class DiffHordeConfig:
    eta: float = 1e-3
    beta: float = 1.0
    rho_clip: float | None = 1.0
    default_gamma: float = 1.0
    default_lambda: float = 0.95
    reduce_cumulants: Literal["mean", "sum"] = "mean"


def diff_horde_init_state(
    *, num_agents: int, num_cumulants: int, device: torch.device, dtype: torch.dtype
) -> TensorDict:
    phi_bar_agentF = torch.zeros((num_agents, num_cumulants), device=device, dtype=dtype)
    return TensorDict({"phi_bar_agentF": phi_bar_agentF}, batch_size=[num_agents], device=device)


def diff_horde_update_phi_bar_agents(
    *,
    phi_bar_agentF: Tensor,
    agent_ids_b: Tensor,
    phi_bF: Tensor,
    eta: float,
) -> Tensor:
    """Functional update: returns a new tensor, does not mutate `phi_bar_agentF`."""
    phi_bar_next = phi_bar_agentF.clone()
    return diff_horde_update_phi_bar_agents_(
        phi_bar_agentF=phi_bar_next,
        agent_ids_b=agent_ids_b,
        phi_bF=phi_bF,
        eta=eta,
    )


def diff_horde_update_phi_bar_agents_(
    *,
    phi_bar_agentF: Tensor,
    agent_ids_b: Tensor,
    phi_bF: Tensor,
    eta: float,
) -> Tensor:
    """In-place update: mutates and returns `phi_bar_agentF`."""
    if phi_bar_agentF.dim() != 2:
        raise ValueError(f"Expected phi_bar_agentF with shape [N_agents,F], got {tuple(phi_bar_agentF.shape)}")
    if agent_ids_b.dim() != 1:
        raise ValueError(f"Expected agent_ids_b with shape [B], got {tuple(agent_ids_b.shape)}")
    if phi_bF.dim() != 2:
        raise ValueError(f"Expected phi_bF with shape [B,F], got {tuple(phi_bF.shape)}")
    if phi_bF.shape[1] != phi_bar_agentF.shape[1]:
        raise ValueError("phi_bF must have the same F as phi_bar_agentF")

    agent_ids_long = agent_ids_b.to(dtype=torch.int64)
    current = phi_bar_agentF[agent_ids_long]
    phi_bar_agentF[agent_ids_long] = current + float(eta) * (phi_bF - current)
    return phi_bar_agentF


def diff_horde_rollout_baseline_step(
    *,
    state: TensorDict,
    agent_ids_b: Tensor,
    phi_bF: Tensor,
    eta: float,
) -> tuple[Tensor, TensorDict]:
    phi_bar_agentF: Tensor = state["phi_bar_agentF"]
    agent_ids_long = agent_ids_b.to(dtype=torch.int64)
    baseline_bF = phi_bar_agentF[agent_ids_long]
    with torch.no_grad():
        diff_horde_update_phi_bar_agents_(
            phi_bar_agentF=phi_bar_agentF,
            agent_ids_b=agent_ids_long,
            phi_bF=phi_bF,
            eta=eta,
        )
    return baseline_bF, state


def diff_horde_sequence_losses(
    *,
    psi_btF: Tensor,
    h_btF: Tensor,
    phi_btF: Tensor,
    phi_bar_btF: Tensor,
    resets_bt: Tensor,
    gamma: float | Tensor | None = None,
    lambda_: float | Tensor | None = None,
    rho_bt: Tensor | None = None,
    cfg: DiffHordeConfig | None = None,
) -> tuple[Tensor, dict[str, Tensor]]:
    if psi_btF.shape != h_btF.shape or psi_btF.shape != phi_btF.shape or psi_btF.shape != phi_bar_btF.shape:
        raise ValueError("psi_btF, h_btF, phi_btF, phi_bar_btF must all have shape [B,T,F]")

    _, t, _ = psi_btF.shape
    if t <= 1:
        zero = psi_btF.sum() * 0.0
        return zero, {"loss": zero}

    cfg_eff = cfg or DiffHordeConfig()
    gamma_eff: float | Tensor = cfg_eff.default_gamma if gamma is None else gamma
    lambda_eff: float | Tensor = cfg_eff.default_lambda if lambda_ is None else lambda_

    delta_lambda, metrics = diff_horde_delta_lambda(
        psi_btF=psi_btF,
        phi_btF=phi_btF,
        phi_bar_btF=phi_bar_btF,
        resets_bt=resets_bt,
        gamma=gamma_eff,
        lambda_=lambda_eff,
        rho_bt=rho_bt,
        rho_clip=cfg_eff.rho_clip,
    )

    psi_t = psi_btF[:, :-1, :]
    h_t = h_btF[:, :-1, :]

    def reduce_fn(x: Tensor) -> Tensor:
        if cfg_eff.reduce_cumulants == "sum":
            reduced = x.sum(dim=-1)
        elif cfg_eff.reduce_cumulants == "mean":
            reduced = x.mean(dim=-1)
        else:
            raise ValueError(f"Unknown reduce_cumulants={cfg_eff.reduce_cumulants!r}")
        return reduced.mean()

    term1 = h_t.detach() * delta_lambda
    term2 = (delta_lambda.detach() - h_t.detach()) * psi_t
    critic_loss = reduce_fn(term1) - reduce_fn(term2)

    h_mse = (delta_lambda.detach() - h_t).pow(2)
    aux_loss = 0.5 * reduce_fn(h_mse)

    total_loss = critic_loss + aux_loss
    metrics.update(
        {
            "loss": total_loss.detach(),
            "critic_loss": critic_loss.detach(),
            "aux_loss": aux_loss.detach(),
            "h_mse": h_mse.detach().mean(),
        }
    )
    return total_loss, metrics


__all__ = [
    "DiffHordeConfig",
    "diff_horde_delta",
    "diff_horde_delta_lambda",
    "diff_horde_forward_view_residual",
    "diff_horde_init_state",
    "diff_horde_sequence_losses",
    "diff_horde_update_phi_bar_agents",
    "diff_horde_update_phi_bar_agents_",
    "diff_horde_rollout_baseline_step",
    "gather_action_values",
    "reverse_discounted_sum",
]
