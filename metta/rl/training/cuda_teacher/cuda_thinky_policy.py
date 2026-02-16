"""CUDA implementation of the thinky scripted teacher agent."""

from __future__ import annotations

import hashlib
from pathlib import Path

import torch
from torch.utils.cpp_extension import load

from metta.rl.training.cuda_teacher import register_cuda_teacher
from mettagrid.policy.policy_env_interface import PolicyEnvInterface

CUDA_DIR = Path(__file__).parent


def _sources_hash() -> str:
    """Hash all CUDA source and header files to detect changes.

    torch.utils.cpp_extension.load() only tracks files listed in sources=[]
    for cache invalidation. Header files (.cuh) included transitively are NOT
    tracked, so changes to them (e.g. MAP_W/MAP_H in common.cuh) would use a
    stale cached binary. Including a content hash in the extension name forces
    recompilation when any file changes.
    """
    h = hashlib.md5()
    for pattern in ("*.cu", "kernels/*.cuh"):
        for f in sorted(CUDA_DIR.glob(pattern)):
            h.update(f.read_bytes())
    return h.hexdigest()[:8]


def _build_id_maps(pei: PolicyEnvInterface) -> dict:
    """Extract action/feature/tag/vibe IDs from PolicyEnvInterface."""

    # Feature IDs by name
    feat = {f.name: f.id for f in pei.obs_features}

    # Action IDs (index in action_names)
    act = {name: idx for idx, name in enumerate(pei.action_names)}

    # Tag IDs (index in tags list)
    tag = {name: idx for idx, name in enumerate(pei.tags)}

    # Vibe IDs: derived from change_vibe_* actions in order
    vibe_names: list[str] = []
    for name in pei.action_names:
        if name.startswith("change_vibe_"):
            vibe_names.append(name[len("change_vibe_") :])
    vibe = {name: idx for idx, name in enumerate(vibe_names)}

    # Inventory token base: normalization of first inv:* feature
    inv_token_base = 0
    for f in pei.obs_features:
        if f.name.startswith("inv:") and ":p" not in f.name:
            inv_token_base = int(f.normalization)
            break

    return {
        "feat": feat,
        "act": act,
        "tag": tag,
        "vibe": vibe,
        "inv_token_base": inv_token_base,
    }


def _get_feat(d: dict, key: str) -> int:
    """Look up a feature ID, returning -1 if absent.

    -1 is safe because CUDA feat_id is uint8 (0-255), so int16_t(-1) will never match.
    """
    return d.get(key, -1)


def _get_tag(d: dict, key: str) -> int:
    """Look up a tag by name, trying plain, type:, and type:c: prefixed variants.

    Returns -2 if absent. -2 is safe because CellCompact.tag uses -1 for "no tag",
    so -2 will never match any real or empty cell.
    """
    for variant in (key, f"type:{key}", f"type:c:{key}"):
        if variant in d:
            return d[variant]
    return -2


def _get_act(d: dict, key: str, fallback: str | None = None, default: int = 0) -> int:
    """Look up an action, with optional fallback name.

    Nim maps both "change_vibe_heart_a" and "change_vibe_heart" to vibeHeartA.
    """
    if key in d:
        return d[key]
    if fallback and fallback in d:
        return d[fallback]
    return default


@register_cuda_teacher("thinky")
class CudaThinkyPolicy:
    def __init__(self, policy_env_info: PolicyEnvInterface, device: torch.device):
        self.device = device

        # Compile CUDA extension (hash in name forces rebuild on header changes)
        self._ext = load(
            name=f"thinky_cuda_{_sources_hash()}",
            sources=[str(CUDA_DIR / "thinky_cuda.cu")],
            extra_include_paths=[str(CUDA_DIR)],
            extra_cuda_cflags=["-O3", "--use_fast_math"],
            verbose=False,
        )

        ids = _build_id_maps(policy_env_info)
        feat = ids["feat"]
        act = ids["act"]
        tag = ids["tag"]

        obs_half_w = policy_env_info.obs_width // 2
        obs_half_h = policy_env_info.obs_height // 2
        num_tokens = policy_env_info.observation_shape[0]
        token_dim = policy_env_info.observation_shape[1]

        # Upload config to CUDA constant memory
        # Nim maps both _a/_b suffixed and plain names to the same action slots:
        #   change_vibe_heart_a OR change_vibe_heart → vibeHeartA
        #   change_vibe_heart_b                      → vibeHeartB (0 if absent)
        self._ext.set_config(
            # Action IDs (0 = noop fallback for missing actions)
            _get_act(act, "noop"),
            _get_act(act, "move_north"),
            _get_act(act, "move_south"),
            _get_act(act, "move_west"),
            _get_act(act, "move_east"),
            _get_act(act, "change_vibe_carbon_a", "change_vibe_carbon"),
            _get_act(act, "change_vibe_carbon_b"),
            _get_act(act, "change_vibe_oxygen_a", "change_vibe_oxygen"),
            _get_act(act, "change_vibe_oxygen_b"),
            _get_act(act, "change_vibe_germanium_a", "change_vibe_germanium"),
            _get_act(act, "change_vibe_germanium_b"),
            _get_act(act, "change_vibe_silicon_a", "change_vibe_silicon"),
            _get_act(act, "change_vibe_silicon_b"),
            _get_act(act, "change_vibe_heart_a", "change_vibe_heart"),
            _get_act(act, "change_vibe_heart_b"),
            _get_act(act, "change_vibe_junction"),
            # Feature IDs (-1 sentinel for missing features; uint8 feat_id never equals -1)
            _get_feat(feat, "tag"),
            _get_feat(feat, "agent:group"),
            _get_feat(feat, "vibe"),
            _get_feat(feat, "last_action"),
            _get_feat(feat, "inv:energy"),
            _get_feat(feat, "inv:carbon"),
            _get_feat(feat, "inv:oxygen"),
            _get_feat(feat, "inv:germanium"),
            _get_feat(feat, "inv:silicon"),
            _get_feat(feat, "inv:heart"),
            _get_feat(feat, "inv:decoder"),
            _get_feat(feat, "inv:modulator"),
            _get_feat(feat, "inv:resonator"),
            _get_feat(feat, "inv:scrambler"),
            _get_feat(feat, "remaining_uses"),
            _get_feat(feat, "inv:carbon:p1"),
            _get_feat(feat, "inv:carbon:p2"),
            _get_feat(feat, "inv:oxygen:p1"),
            _get_feat(feat, "inv:oxygen:p2"),
            _get_feat(feat, "inv:germanium:p1"),
            _get_feat(feat, "inv:germanium:p2"),
            _get_feat(feat, "inv:silicon:p1"),
            _get_feat(feat, "inv:silicon:p2"),
            _get_feat(feat, "inv:heart:p1"),
            _get_feat(feat, "inv:heart:p2"),
            _get_feat(feat, "protocol_input:carbon"),
            _get_feat(feat, "protocol_input:oxygen"),
            _get_feat(feat, "protocol_input:germanium"),
            _get_feat(feat, "protocol_input:silicon"),
            _get_feat(feat, "protocol_output:heart"),
            _get_feat(feat, "lp:east"),
            _get_feat(feat, "lp:west"),
            _get_feat(feat, "lp:north"),
            _get_feat(feat, "lp:south"),
            # Tag IDs (try plain, type:, and type:c: prefixes)
            _get_tag(tag, "agent"),
            _get_tag(tag, "wall"),
            _get_tag(tag, "hub"),
            _get_tag(tag, "chest"),
            _get_tag(tag, "junction"),
            _get_tag(tag, "carbon_extractor"),
            _get_tag(tag, "oxygen_extractor"),
            _get_tag(tag, "germanium_extractor"),
            _get_tag(tag, "silicon_extractor"),
            # Vibe IDs — hardcoded to match Nim's Vibes struct defaults.
            # The Nim code never populates these from config; they're fixed.
            0,  # default
            1,  # junction
            2,  # carbon_a
            3,  # carbon_b
            4,  # oxygen_a
            5,  # oxygen_b
            6,  # germanium_a
            7,  # germanium_b
            8,  # silicon_a
            9,  # silicon_b
            10,  # heart_a
            11,  # heart_b
            # Observation dims
            obs_half_w,
            obs_half_h,
            num_tokens,
            token_dim,
            ids["inv_token_base"],
        )

        self._states: torch.Tensor | None = None
        self._num_agents: int | None = None

    def step_batch(
        self,
        observations: torch.Tensor,
        actions: torch.Tensor,
        dones: torch.Tensor | None = None,
    ) -> None:
        """Compute teacher actions for all agents, in-place.

        Args:
            observations: [N, num_tokens, token_dim] uint8 on GPU.
            actions: [N] int64 on GPU, filled in-place.
            dones: [N] bool on GPU, optional. Resets agent state on episode boundaries.
        """
        N = observations.shape[0]

        if self._states is None or self._num_agents != N:
            self._states = self._ext.init_states(N, self.device)
            self._num_agents = N

        self._ext.teacher_step(observations, actions, self._states, dones)
