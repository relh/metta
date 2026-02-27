"""
Put the M in MARL :)

This module exists to host non-learning policies (NPCs, teachers, scripted opponents, etc.) alongside trainable ones.
It also supports multiple trainable policies at once, each with its own optimizer configuration.
"""

from __future__ import annotations

from typing import Literal, Mapping

from pydantic import Field, model_validator

from metta.agent.policies.default import DefaultPolicyConfig
from metta.agent.policy import Policy, PolicyArchitecture
from mettagrid.base_config import Config


class OptimizerConfig(Config):
    type: Literal["adam", "muon", "adamw_schedulefree", "sgd_schedulefree"] = "adamw_schedulefree"
    # Learning rate tuned from CvC sweep winners (schedule-free AdamW)
    learning_rate: float = Field(default=0.00737503357231617, gt=0, le=1.0)
    # Beta1: Standard Adam default from Kingma & Ba (2014) "Adam: A Method for Stochastic Optimization"
    beta1: float = Field(default=0.9, ge=0, le=1.0)
    # Beta2: Standard Adam default from Kingma & Ba (2014)
    beta2: float = Field(default=0.999, ge=0, le=1.0)
    # Epsilon tuned from CvC sweep winners
    eps: float = Field(default=5.0833278919526e-07, gt=0)
    # Weight decay: modest L2 regularization for AdamW-style optimizers
    weight_decay: float = Field(default=0.01, ge=0)
    # ScheduleFree-specific parameters
    momentum: float = Field(default=0.9, ge=0, le=1.0)  # Beta parameter for ScheduleFree
    warmup_steps: int = Field(default=1000, ge=0)  # Number of warmup steps for ScheduleFree


class PolicyAssetConfig(Config):
    """Declarative spec for a policy asset.

    A policy asset can either be loaded from a URI or created from an architecture.
    """

    uri: str | None = None
    run: str | None = None
    architecture: PolicyArchitecture | None = Field(default_factory=DefaultPolicyConfig)

    # Whether this policy should be checkpointed during training.
    checkpoint: bool = True

    # Whether this policy is trainable (affects parameter freezing and optimizer creation).
    trainable: bool = True

    # Set to None for frozen/non-trainable policies or to disable optimization.
    optimizer: OptimizerConfig | None = Field(default_factory=OptimizerConfig)

    @model_validator(mode="after")
    def _validate_asset(self) -> "PolicyAssetConfig":
        if self.uri is None and self.architecture is None:
            raise ValueError("PolicyAssetConfig must provide at least one of: uri, architecture")
        if not self.trainable:
            self.optimizer = None
        return self


class PolicyAssetRegistry:
    """Runtime registry of named policy assets."""

    def __init__(
        self,
        *,
        configs: Mapping[str, PolicyAssetConfig],
        policies: Mapping[str, Policy],
    ) -> None:
        self._configs = dict(configs)
        self._policies = dict(policies)

        # Validate that configs and policies have matching keys
        config_keys = set(self._configs)
        policy_keys = set(self._policies)
        if config_keys != policy_keys:
            missing_in_policies = config_keys - policy_keys
            missing_in_configs = policy_keys - config_keys
            errors = []
            if missing_in_policies:
                errors.append(f"configs without policies: {sorted(missing_in_policies)}")
            if missing_in_configs:
                errors.append(f"policies without configs: {sorted(missing_in_configs)}")
            raise ValueError(f"PolicyAssetRegistry configs and policies keys must match. {', '.join(errors)}")

        trainable_namespaces: dict[str, str] = {}
        for policy_name, cfg in self._configs.items():
            if not cfg.trainable or cfg.optimizer is None:
                continue
            namespace = cfg.run or cfg.uri
            if namespace is None:
                raise ValueError(
                    f"Trainable policy asset '{policy_name}' must define a run or uri for checkpoint namespace"
                )
            if namespace in trainable_namespaces:
                other = trainable_namespaces[namespace]
                raise ValueError(
                    "Trainable policy assets must have unique run/uri namespaces "
                    f"(shared={namespace!r} between '{other}' and '{policy_name}')"
                )
            trainable_namespaces[namespace] = policy_name

    @property
    def policies(self) -> dict[str, Policy]:
        return self._policies

    @property
    def configs(self) -> dict[str, PolicyAssetConfig]:
        return self._configs

    def get(self, name: str) -> Policy:
        if name not in self._policies:
            available = sorted(self._policies)
            raise KeyError(f"Policy '{name}' not found in PolicyAssetRegistry. Available policies: {available}")
        return self._policies[name]

    def get_config(self, name: str) -> PolicyAssetConfig:
        if name not in self._configs:
            available = sorted(self._configs)
            raise KeyError(f"Policy config '{name}' not found in PolicyAssetRegistry. Available configs: {available}")
        return self._configs[name]
