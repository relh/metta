from pydantic import Field

from metta.rl.loss.loss import LossConfig
from metta.rl.loss.ppo_actor import PPOActorConfig
from metta.rl.loss.ppo_critic import PPOCriticConfig
from mettagrid.base_config import Config
from mettagrid.policy.policy_env_interface import PolicyEnvInterface


class LossesConfig(Config):
    # Loss configs are stored in insertion order.
    losses: dict[str, LossConfig] = Field(default_factory=lambda: LossesConfig._default_losses())

    @classmethod
    def _default_losses(cls) -> dict[str, LossConfig]:
        # Insertion order defines execution order. You can override, remove, or add entries after init.
        return {
            "ppo_critic": PPOCriticConfig(),
            "ppo_actor": PPOActorConfig(),
        }

    def _configs(self) -> dict[str, LossConfig]:
        # Return losses in insertion order.
        return self.losses

    @property
    def loss_configs(self) -> dict[str, LossConfig]:
        return self._configs()

    def __iter__(self):
        """Iterate over (name, config) pairs for all loss configs (in insertion order)."""
        for name, cfg in self.losses.items():
            yield name, cfg

    def __getattr__(self, item: str) -> LossConfig:
        losses = object.__getattribute__(self, "losses")
        if item in losses:
            return losses[item]
        return super().__getattr__(item)

    def has_loss(self, key: str) -> bool:
        return key in self.losses

    def add_loss(self, key: str, value: LossConfig) -> None:
        if key in self.losses:
            raise KeyError(f"Loss '{key}' already exists.")
        self.losses[key] = value

    def replace_loss(self, key: str, value: LossConfig) -> None:
        self.losses[key] = value

    # Convenience dict-style access
    def __getitem__(self, key: str) -> LossConfig:
        return self.losses[key]

    def __setitem__(self, key: str, value: LossConfig) -> None:
        self.losses[key] = value

    def __delitem__(self, key: str) -> None:
        del self.losses[key]

    @staticmethod
    def _is_vibe_actor_cfg(cfg: PPOActorConfig) -> bool:
        return cfg.actor_name == "vibe" or cfg.log_prob_key.startswith("vibe_") or cfg.entropy_key.startswith("vibe_")

    @staticmethod
    def _ensure_action_key(cfg: PPOActorConfig, key: str) -> None:
        if key not in cfg.extra_action_keys:
            cfg.extra_action_keys = [*cfg.extra_action_keys, key]

    def configure_for_policy_env(
        self,
        *,
        policy_env_info: PolicyEnvInterface,
        trajectory_isolation: object | None = None,
    ) -> None:
        """Reconcile actor losses with split-action envs (walk + vibe/chat)."""
        has_vibe_actions = bool(policy_env_info.vibe_action_names)
        base_actor_cfg = self.losses.get("ppo_actor")
        base_actor = base_actor_cfg if isinstance(base_actor_cfg, PPOActorConfig) else None

        if has_vibe_actions:
            if base_actor is not None:
                self._ensure_action_key(base_actor, "vibe_actions")

            vibe_loss_names: list[str] = []
            for name, cfg in self.losses.items():
                if not isinstance(cfg, PPOActorConfig):
                    continue
                if not self._is_vibe_actor_cfg(cfg):
                    continue
                vibe_loss_names.append(name)
                self._ensure_action_key(cfg, "vibe_actions")

            if not vibe_loss_names and base_actor is not None:
                split_loss_coef = float(base_actor.loss_coef) / 2.0
                base_actor.loss_coef = split_loss_coef
                self.add_loss(
                    "ppo_vibe_actor",
                    PPOActorConfig(
                        actor_name="vibe",
                        log_prob_key="vibe_act_log_prob",
                        entropy_key="vibe_entropy",
                        loss_coef=split_loss_coef,
                        replay_ratio_key="vibe_ratio",
                        extra_action_keys=["vibe_actions"],
                    ),
                )
                vibe_loss_names = ["ppo_vibe_actor"]

            if trajectory_isolation is not None and "ppo_vibe_actor" in vibe_loss_names:
                for slice_cfg in getattr(trajectory_isolation, "slices", []):
                    losses = getattr(slice_cfg, "losses", None)
                    if not isinstance(losses, list):
                        continue
                    if "ppo_actor" not in losses or "ppo_vibe_actor" in losses:
                        continue
                    insert_at = losses.index("ppo_actor") + 1
                    losses.insert(insert_at, "ppo_vibe_actor")
            return

        to_remove: list[str] = []
        restored_loss_coef = 0.0
        for name, cfg in self.losses.items():
            if not isinstance(cfg, PPOActorConfig):
                continue
            if "vibe_actions" in cfg.extra_action_keys:
                cfg.extra_action_keys = [key for key in cfg.extra_action_keys if key != "vibe_actions"]
            if self._is_vibe_actor_cfg(cfg):
                to_remove.append(name)
                restored_loss_coef += float(cfg.loss_coef)

        if not to_remove:
            return

        for name in to_remove:
            self.losses.pop(name, None)

        if base_actor is not None and restored_loss_coef > 0:
            base_actor.loss_coef = float(base_actor.loss_coef) + restored_loss_coef

        if trajectory_isolation is not None:
            for slice_cfg in getattr(trajectory_isolation, "slices", []):
                losses = getattr(slice_cfg, "losses", None)
                if isinstance(losses, list):
                    slice_cfg.losses = [loss for loss in losses if loss not in to_remove]
