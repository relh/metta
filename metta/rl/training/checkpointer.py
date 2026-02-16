"""Policy checkpoint management component."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Optional, cast

import torch
from pydantic import Field
from safetensors.torch import load_file as load_safetensors_file

from metta.agent.policy import Policy, PolicyArchitecture
from metta.rl.checkpoint_manager import CheckpointManager
from metta.rl.training import DistributedHelper, TrainerComponent
from metta.rl.training.optimizer import is_schedulefree_optimizer
from mettagrid.base_config import Config
from mettagrid.policy.loader import initialize_or_load_policy
from mettagrid.policy.policy_env_interface import PolicyEnvInterface
from mettagrid.util.module import load_symbol
from mettagrid.util.uri_resolvers.schemes import policy_spec_from_uri, resolve_uri

logger = logging.getLogger(__name__)


class CheckpointerConfig(Config):
    epoch_interval: int = Field(default=30, ge=0)


class Checkpointer(TrainerComponent):
    """Manages policy checkpointing with distributed awareness."""

    def __init__(
        self,
        *,
        config: CheckpointerConfig,
        checkpoint_manager: CheckpointManager,
        distributed_helper: DistributedHelper,
        policy_architecture: PolicyArchitecture | None,
        policy_getter: Callable[[], Policy] | None = None,
        policy_name: str | None = None,
    ) -> None:
        super().__init__(epoch_interval=max(1, config.epoch_interval))
        self._master_only = True
        self._config = config
        self._checkpoint_manager = checkpoint_manager
        self._distributed = distributed_helper
        self._policy_architecture: PolicyArchitecture | None = policy_architecture
        self._latest_policy_uri: Optional[str] = None
        self._policy_getter = policy_getter
        self._policy_name = policy_name

    @property
    def policy_architecture(self) -> PolicyArchitecture | None:
        return self._policy_architecture

    def register(self, context) -> None:
        super().register(context)
        if not self._policy_name:
            raise ValueError("Checkpointer requires policy_name when using multi-policy assets")
        latest_uris = getattr(context, "latest_policy_uris", None)
        if latest_uris is None:
            latest_uris = {}
            context.latest_policy_uris = latest_uris
        latest_uris[self._policy_name] = self.get_latest_policy_uri()

    def load_or_create_policy(
        self,
        policy_env_info: PolicyEnvInterface,
        *,
        policy_uri: Optional[str] = None,
    ) -> Any:  # Returns Policy or MultiAgentPolicy
        """Load the latest policy checkpoint or create a new policy."""
        candidate_uri = policy_uri or self._checkpoint_manager.get_latest_checkpoint()
        load_device = torch.device(self._distributed.config.device)

        if self._distributed.is_distributed:
            normalized_uri = self._distributed.broadcast_from_master(
                resolve_uri(candidate_uri).canonical if self._distributed.is_master() and candidate_uri else None
            )

            if normalized_uri:
                payload: tuple[str, dict[str, object], dict[str, torch.Tensor]] | None = None
                if self._distributed.is_master():
                    policy_spec = policy_spec_from_uri(normalized_uri)
                    assert policy_spec.data_path is not None, "policy_spec.data_path must be set"
                    state_dict = load_safetensors_file(str(Path(policy_spec.data_path).expanduser()))
                    payload = (
                        policy_spec.class_path,
                        policy_spec.init_kwargs or {},
                        {k: v.cpu() for k, v in state_dict.items()},
                    )
                payload = self._distributed.broadcast_from_master(payload)
                assert payload is not None, "broadcast_from_master must return non-None payload"
                class_path, init_kwargs, state_dict = payload
                init_kwargs = dict(init_kwargs)
                self._ensure_policy_code_available(
                    normalized_uri=normalized_uri,
                    class_path=class_path,
                    init_kwargs=init_kwargs,
                )
                self._set_architecture_from_checkpoint(class_path, init_kwargs)
                if "device" in init_kwargs:
                    init_kwargs["device"] = str(load_device)
                policy_class = cast(Callable[..., Any], load_symbol(class_path))
                policy = policy_class(policy_env_info, **init_kwargs)
                if hasattr(policy, "to"):
                    policy = policy.to(load_device)
                policy.load_state_dict(state_dict, strict=True)
                initialize = getattr(policy, "initialize_to_environment", None)
                if callable(initialize):
                    initialize(policy_env_info, load_device)

                if self._distributed.is_master():
                    self._latest_policy_uri = normalized_uri
                    logger.info("Loaded policy from %s", normalized_uri)
                return policy

        if candidate_uri:
            policy_spec = policy_spec_from_uri(candidate_uri)
            self._set_architecture_from_checkpoint(policy_spec.class_path, policy_spec.init_kwargs or {})
            policy = initialize_or_load_policy(policy_env_info, policy_spec, device_override=str(load_device))
            self._latest_policy_uri = resolve_uri(candidate_uri).canonical
            logger.info("Loaded policy from %s", candidate_uri)
            return policy

        logger.info("Creating new policy for training run")
        if self._policy_architecture is None:
            raise ValueError("Cannot create a new policy without a policy_architecture")
        return self._policy_architecture.make_policy(policy_env_info)

    def _set_architecture_from_checkpoint(self, class_path: str, init_kwargs: dict[str, object]) -> None:
        if class_path != "metta.agent.policy.CheckpointPolicy":
            return
        architecture_spec = init_kwargs.get("architecture_spec")
        if not isinstance(architecture_spec, str) or not architecture_spec:
            raise ValueError("Checkpoint policy spec is missing architecture_spec.")
        self._policy_architecture = PolicyArchitecture.from_spec(architecture_spec)

    def _ensure_policy_code_available(
        self,
        *,
        normalized_uri: str,
        class_path: str,
        init_kwargs: dict[str, object],
    ) -> None:
        if self._distributed.is_master():
            return

        needs_spec = load_symbol(class_path, strict=False) is None
        if not needs_spec and class_path == "metta.agent.policy.CheckpointPolicy":
            architecture_spec = init_kwargs.get("architecture_spec")
            if isinstance(architecture_spec, str) and architecture_spec:
                try:
                    PolicyArchitecture.from_spec(architecture_spec)
                except (ImportError, ModuleNotFoundError, AttributeError, TypeError):
                    needs_spec = True

        if needs_spec:
            policy_spec_from_uri(normalized_uri)

    def get_latest_policy_uri(self) -> Optional[str]:
        return self._checkpoint_manager.get_latest_checkpoint() or self._latest_policy_uri

    def on_epoch_end(self, epoch: int) -> None:
        if not self._distributed.should_checkpoint():
            return
        self._save_policy(epoch)

    def on_training_complete(self) -> None:
        if not self._distributed.should_checkpoint():
            return
        self._save_policy(self.context.epoch)

    def _save_policy(self, epoch: int) -> None:
        policy = self._policy_getter() if self._policy_getter is not None else self.context.policy
        if policy is None:
            raise RuntimeError("Checkpointer requires a policy instance to save checkpoints.")
        if self._policy_architecture is None:
            raise ValueError("Cannot save policy checkpoint without policy_architecture")

        optimizer_state = None
        optimizer = getattr(policy, "optimizer", None)
        is_schedulefree = optimizer is not None and is_schedulefree_optimizer(optimizer)
        if optimizer is not None:
            if is_schedulefree:
                optimizer.eval()
            optimizer_state = optimizer.state_dict()

        uri = self._checkpoint_manager.save_policy_checkpoint(
            state_dict=policy.state_dict(),
            architecture=self._policy_architecture,
            epoch=epoch,
            optimizer_state=optimizer_state,
        )

        if is_schedulefree:
            assert optimizer is not None
            optimizer.train()

        self._latest_policy_uri = uri
        latest_uris = getattr(self.context, "latest_policy_uris", None)
        if latest_uris is None:
            latest_uris = {}
            self.context.latest_policy_uris = latest_uris
        latest_uris[self._policy_name] = uri
        self.context.latest_saved_policy_epoch = epoch

        # Log latest checkpoint URI to wandb if available
        stats_reporter = getattr(self.context, "stats_reporter", None)
        wandb_run = getattr(stats_reporter, "wandb_run", None) if stats_reporter is not None else None
        if wandb_run is not None:
            wandb_run.log(
                {
                    "checkpoint/latest_uri": uri,
                    "checkpoint/latest_epoch": float(epoch),
                    f"checkpoint/{self._policy_name}/latest_uri": uri,
                    f"checkpoint/{self._policy_name}/latest_epoch": float(epoch),
                },
                step=self.context.agent_step,
            )
            logger.info(f"Logged checkpoint URI to wandb: {uri}")
