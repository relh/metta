from pydantic import Field

from metta.rl.loss.loss import LossConfig
from metta.rl.loss.ppo_actor import PPOActorConfig
from metta.rl.loss.ppo_critic import PPOCriticConfig
from mettagrid.base_config import Config


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
