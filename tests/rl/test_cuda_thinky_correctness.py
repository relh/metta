"""Correctness test: compare CUDA thinky teacher actions against Nim reference.

Runs episodes on multiple map types and agent counts, feeding identical
observations to both the Nim thinky agent and the CUDA thinky kernel.
Reports per-step agreement rate.

Requires a CUDA GPU to run (the CUDA extension is JIT-compiled on first use).

Note on exploration RNG: When agents have no visible targets (extractors, hubs,
chests), both systems enter exploration mode and pick random directions. The CUDA
kernel and Nim use independent RNGs, so exploration directions will differ. This
only affects agents on large maps that spawn far from any target. Once targets are
found, both systems agree on pathfinding. Tests on small/dense maps (diagnostic,
machina1 with enough cogs) show 100% agreement.
"""

import numpy as np
import pytest
import torch

from cogames.cli.mission import get_mission
from mettagrid.envs.mettagrid_puffer_env import MettaGridPufferEnv
from mettagrid.policy.loader import discover_and_register_policies
from mettagrid.policy.policy import PolicySpec
from mettagrid.policy.policy_env_interface import PolicyEnvInterface
from mettagrid.simulator import Simulator

# Skip entire module when CUDA is unavailable
pytestmark = pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA not available")

_SUPERVISOR_SPEC = PolicySpec(class_path="cogames_agents.policy.nim_agents.agents.ThinkyAgentsMultiPolicy")


def _make_env(mission: str, cogs: int, max_steps: int, seed: int = 42):
    """Create a test environment with thinky supervisor."""
    discover_and_register_policies("cogames.policy")
    discover_and_register_policies("cogames_agents.policy")

    _, env_cfg, _ = get_mission(mission, variants_arg=None, cogs=cogs)
    env_cfg.game.max_steps = max_steps

    simulator = Simulator()
    env = MettaGridPufferEnv(simulator, env_cfg, supervisor_policy_spec=_SUPERVISOR_SPEC)
    env.reset(seed=seed)

    policy_env_info = PolicyEnvInterface.from_mg_cfg(env_cfg)
    return env, env_cfg, policy_env_info


def _run_comparison(mission: str, cogs: int, num_steps: int, seed: int = 42):
    """Run both Nim and CUDA thinky on identical observations and return agreement stats."""
    from metta.rl.training.cuda_teacher.cuda_thinky_policy import CudaThinkyPolicy  # noqa: PLC0415

    device = torch.device("cuda:0")
    env, env_cfg, policy_env_info = _make_env(mission, cogs, max_steps=num_steps + 10, seed=seed)
    cuda_teacher = CudaThinkyPolicy(policy_env_info, device)

    num_agents = env_cfg.game.num_agents
    noop_idx = list(policy_env_info.action_names).index("noop")

    total_actions = 0
    matching_actions = 0
    mismatches_by_step: list[dict] = []

    for step_i in range(num_steps):
        obs = env.observations
        nim_actions = env.teacher_actions.copy()

        obs_gpu = torch.as_tensor(np.ascontiguousarray(obs), dtype=torch.uint8, device=device)
        cuda_actions_gpu = torch.zeros(num_agents, dtype=torch.int64, device=device)
        cuda_teacher.step_batch(obs_gpu, cuda_actions_gpu)
        cuda_actions = cuda_actions_gpu.cpu().numpy().astype(np.int32)

        match = nim_actions == cuda_actions
        total_actions += num_agents
        matching_actions += int(match.sum())

        if not match.all():
            mismatches_by_step.append(
                {
                    "step": step_i,
                    "mismatched_agents": int((~match).sum()),
                    "nim": nim_actions[~match].tolist(),
                    "cuda": cuda_actions[~match].tolist(),
                }
            )

        noop_actions = np.full(num_agents, noop_idx, dtype=np.int32)
        env.step(noop_actions)

    env.close()

    agreement_pct = 100.0 * matching_actions / total_actions if total_actions > 0 else 0.0
    print(f"\n=== {mission} (cogs={cogs}, seed={seed}) ===")
    print(f"Steps: {num_steps}, Agents: {num_agents}")
    print(f"Total actions: {total_actions}")
    print(f"Matching: {matching_actions} ({agreement_pct:.1f}%)")
    print(f"Mismatched steps: {len(mismatches_by_step)}/{num_steps}")

    if mismatches_by_step:
        print("First 5 mismatches:")
        for m in mismatches_by_step[:5]:
            print(f"  Step {m['step']}: {m['mismatched_agents']} agents differ")
            print(f"    Nim:  {m['nim'][:5]}")
            print(f"    CUDA: {m['cuda'][:5]}")

    return agreement_pct, total_actions, matching_actions


def test_cuda_thinky_targets_visible():
    """When targets are immediately visible, CUDA and Nim should agree perfectly."""
    # Diagnostic map: small, targets within observation window
    pct, _, _ = _run_comparison("evals.diagnostic_chest_navigation1", cogs=2, num_steps=50)
    assert pct > 95.0, f"Agreement too low on diagnostic map: {pct:.1f}%"


def test_cuda_thinky_machina1_dense():
    """On machina1 with enough agents, most should find targets quickly."""
    pct, _, _ = _run_comparison("cogsguard_machina_1.basic", cogs=8, num_steps=200)
    assert pct > 95.0, f"Agreement too low on machina1 8-cog: {pct:.1f}%"


def test_cuda_thinky_machina1_sparse():
    """On machina1 with fewer agents, exploration RNG causes some divergence.

    Agents far from targets enter exploration mode with different RNGs.
    We accept lower agreement but still expect majority of actions to match.
    """
    pct, _, _ = _run_comparison("cogsguard_machina_1.basic", cogs=4, num_steps=200)
    assert pct > 50.0, f"Agreement too low on machina1 4-cog: {pct:.1f}%"
