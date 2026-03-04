from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import Field, model_validator

from metta.agent.components.component_config import ComponentConfig


class DramaWorldModelConfig(ComponentConfig):
    """Config for Drama-inspired world model component."""

    name: str = "drama_world_model"
    in_key: str = "encoded_obs"
    out_key: str = "core"
    action_key: str = "last_actions"

    stoch_dim: int = 48
    action_dim: int = 1
    d_model: int = 96
    d_intermediate: int = 192
    n_layer: int = 1
    dropout_p: float = 0.0

    ssm_cfg: Dict[str, Any] = Field(default_factory=dict)
    attn_layer_idx: list[int] = Field(default_factory=list)
    attn_cfg: Dict[str, Any] = Field(default_factory=dict)
    pff_cfg: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _normalize_legacy_payload(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        normalized = dict(data)
        normalized.pop("pool", None)
        normalized.pop("use_reward_token", None)
        normalized.pop("use_reset_token", None)

        if normalized.get("ssm_cfg") is None:
            normalized["ssm_cfg"] = {}
        if normalized.get("attn_layer_idx") is None:
            normalized["attn_layer_idx"] = []
        if normalized.get("attn_cfg") is None:
            normalized["attn_cfg"] = {}
        if normalized.get("pff_cfg") is None:
            normalized["pff_cfg"] = {}
        return normalized

    def make_component(self, env: Optional[Any] = None):  # type: ignore[override]
        from .world_model_component import DramaWorldModelComponent  # noqa: PLC0415

        resolved = self
        if env is not None:
            action_space = getattr(env, "action_space", None)
            action_dim = getattr(action_space, "n", None)
            if action_dim is not None:
                resolved = self.model_copy(update={"action_dim": max(1, int(action_dim))})

        return DramaWorldModelComponent(config=resolved, env=env)
