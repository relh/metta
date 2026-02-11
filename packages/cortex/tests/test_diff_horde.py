from __future__ import annotations

import torch
from cortex.rl.diff_horde import (
    diff_horde_delta,
    diff_horde_delta_lambda,
    diff_horde_rollout_baseline_step,
    diff_horde_update_phi_bar_agents,
    diff_horde_update_phi_bar_agents_,
    gather_action_values,
    reverse_discounted_sum,
)
from tensordict import TensorDict


def test_gather_action_values_matches_manual() -> None:
    torch.manual_seed(0)
    b, t, a, f = 3, 5, 7, 4
    values = torch.randn(b, t, a, f)
    actions = torch.randint(0, a, (b, t))

    gathered = gather_action_values(values, actions)
    assert gathered.shape == (b, t, f)

    manual = torch.stack(
        [values[i, j, actions[i, j]] for i in range(b) for j in range(t)],
        dim=0,
    ).view(b, t, f)
    torch.testing.assert_close(gathered, manual)


def test_reverse_discounted_sum_matches_loop() -> None:
    torch.manual_seed(0)
    b, t, d = 4, 11, 3
    x = torch.randn(b, t, d)
    discounts = torch.sigmoid(torch.randn(b, t, d))

    out = reverse_discounted_sum(x, discounts)
    assert out.shape == x.shape

    running = torch.zeros((b, d), dtype=x.dtype)
    expected = torch.zeros_like(x)
    for ti in range(t - 1, -1, -1):
        running = x[:, ti, :] + discounts[:, ti, :] * running
        expected[:, ti, :] = running

    torch.testing.assert_close(out, expected, rtol=1e-6, atol=1e-6)


def test_diff_horde_delta_lambda_lambda0_equals_rho_delta() -> None:
    torch.manual_seed(0)
    b, t, f = 2, 6, 5
    psi = torch.randn(b, t, f)
    phi = torch.randn(b, t, f)
    baseline = torch.randn(b, t, f)
    resets = torch.zeros((b, t))

    rho = torch.exp(torch.randn(b, t).clamp(-2, 2))

    delta = diff_horde_delta(psi_btF=psi, phi_btF=phi, phi_bar_btF=baseline, resets_bt=resets, gamma=0.97)
    delta_lambda, _ = diff_horde_delta_lambda(
        psi_btF=psi,
        phi_btF=phi,
        phi_bar_btF=baseline,
        resets_bt=resets,
        gamma=0.97,
        lambda_=0.0,
        rho_bt=rho,
        rho_clip=None,
    )

    expected = rho[:, :-1].unsqueeze(-1) * delta
    torch.testing.assert_close(delta_lambda, expected, rtol=1e-6, atol=1e-6)


def test_diff_horde_resets_block_bootstrap() -> None:
    b, t, f = 1, 4, 1
    psi = torch.zeros((b, t, f))
    phi = torch.ones((b, t, f))
    baseline = torch.zeros((b, t, f))

    resets = torch.tensor([[0.0, 0.0, 1.0, 0.0]])

    delta_lambda, _ = diff_horde_delta_lambda(
        psi_btF=psi,
        phi_btF=phi,
        phi_bar_btF=baseline,
        resets_bt=resets,
        gamma=1.0,
        lambda_=1.0,
    )

    # With delta=1 everywhere, γ=λ=1, and a reset at t=2, expect:
    # Δ_2 = 1
    # Δ_1 = 1 (bootstrap blocked by reset at t+1=2)
    # Δ_0 = 1 + 1*Δ_1 = 2
    expected = torch.tensor([[[2.0], [1.0], [1.0]]])
    torch.testing.assert_close(delta_lambda, expected, rtol=0, atol=0)


def test_diff_horde_update_phi_bar_agents_is_functional() -> None:
    phi_bar = torch.zeros((3, 2))
    agent_ids = torch.tensor([0, 2])
    phi = torch.tensor([[1.0, -1.0], [3.0, 5.0]])
    eta = 0.1

    updated = diff_horde_update_phi_bar_agents(phi_bar_agentF=phi_bar, agent_ids_b=agent_ids, phi_bF=phi, eta=eta)

    assert torch.all(phi_bar == 0)
    expected = torch.zeros_like(phi_bar)
    expected[0] = eta * phi[0]
    expected[2] = eta * phi[1]
    torch.testing.assert_close(updated, expected, rtol=0, atol=0)


def test_diff_horde_update_phi_bar_agents_inplace_mutates() -> None:
    phi_bar = torch.zeros((3, 2))
    agent_ids = torch.tensor([0, 2])
    phi = torch.tensor([[1.0, -1.0], [3.0, 5.0]])
    eta = 0.1

    out = diff_horde_update_phi_bar_agents_(phi_bar_agentF=phi_bar, agent_ids_b=agent_ids, phi_bF=phi, eta=eta)
    assert out is phi_bar

    expected = torch.zeros_like(phi_bar)
    expected[0] = eta * phi[0]
    expected[2] = eta * phi[1]
    torch.testing.assert_close(phi_bar, expected, rtol=0, atol=0)


def test_diff_horde_rollout_baseline_step_snapshot_and_update() -> None:
    state = TensorDict({"phi_bar_agentF": torch.zeros((4, 3))}, batch_size=[4])
    agent_ids = torch.tensor([1, 3])
    phi = torch.tensor([[2.0, 0.0, -2.0], [1.0, 1.0, 1.0]])
    eta = 0.5

    baseline, next_state = diff_horde_rollout_baseline_step(state=state, agent_ids_b=agent_ids, phi_bF=phi, eta=eta)
    assert next_state is state

    torch.testing.assert_close(baseline, torch.zeros_like(phi), rtol=0, atol=0)
    expected = torch.zeros_like(state["phi_bar_agentF"])
    expected[1] = eta * phi[0]
    expected[3] = eta * phi[1]
    torch.testing.assert_close(next_state["phi_bar_agentF"], expected, rtol=0, atol=0)
