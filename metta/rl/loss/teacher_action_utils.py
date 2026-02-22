from __future__ import annotations

import torch
from torch import Tensor


def teacher_action_indices_and_valid_mask(teacher_actions: Tensor, num_actions: int) -> tuple[Tensor, Tensor]:
    """Return long indices plus a mask for labels in [0, num_actions)."""
    teacher_actions_long = teacher_actions.to(dtype=torch.long)
    valid_teacher_actions = (teacher_actions_long >= 0) & (teacher_actions_long < num_actions)
    return teacher_actions_long, valid_teacher_actions


def safe_teacher_action_indices(teacher_actions: Tensor, num_actions: int) -> tuple[Tensor, Tensor, Tensor]:
    """Return long labels, valid mask, and clamped indices safe for gather()."""
    teacher_actions_long, valid_teacher_actions = teacher_action_indices_and_valid_mask(teacher_actions, num_actions)
    safe_actions = teacher_actions_long.clamp(min=0, max=num_actions - 1)
    return teacher_actions_long, valid_teacher_actions, safe_actions


def decode_teacher_action_labels(
    teacher_actions: Tensor,
    *,
    num_primary_actions: int,
    num_vibe_actions: int,
    noop_action_index: int,
) -> tuple[Tensor, Tensor, Tensor, Tensor]:
    """Decode split full-id teacher labels into core/vibe indices.

    Returns:
        core_actions: teacher labels for the non-vibe branch
        core_valid: mask for valid core labels
        vibe_actions: teacher labels for the vibe branch (0 when absent)
        vibe_valid: mask for valid vibe labels
    """
    teacher_actions_long = teacher_actions.to(dtype=torch.long)
    core_actions = torch.full_like(teacher_actions_long, fill_value=noop_action_index)
    vibe_actions = torch.zeros_like(teacher_actions_long)

    # Canonical split-action labels occupy [0, num_primary_actions + num_vibe_actions).
    full_action_count = num_primary_actions + num_vibe_actions
    primary_mask = (teacher_actions_long >= 0) & (teacher_actions_long < num_primary_actions)
    vibe_only_mask = (teacher_actions_long >= num_primary_actions) & (teacher_actions_long < full_action_count)
    core_actions[primary_mask] = teacher_actions_long[primary_mask]
    vibe_actions[vibe_only_mask] = teacher_actions_long[vibe_only_mask] - num_primary_actions
    return core_actions, (primary_mask | vibe_only_mask), vibe_actions, vibe_only_mask
