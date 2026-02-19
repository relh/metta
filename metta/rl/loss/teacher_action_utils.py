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
