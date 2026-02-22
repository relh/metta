"""Trainer state checkpoint management component."""

import logging
from typing import Any, Dict, Optional

import torch

from metta.rl.checkpoint_manager import CheckpointManager
from metta.rl.training import ComponentContext, DistributedHelper, TrainerComponent

logger = logging.getLogger(__name__)


class ContextCheckpointer(TrainerComponent):
    """Persist and restore optimizer/timing state alongside policy checkpoints."""

    trainer_attr = "trainer_checkpointer"

    def __init__(
        self,
        *,
        checkpoint_manager: CheckpointManager,
        distributed_helper: DistributedHelper,
        epoch_interval: int = 1,
    ) -> None:
        super().__init__(epoch_interval=epoch_interval)
        self._checkpoint_manager = checkpoint_manager
        self._distributed = distributed_helper

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------
    def register(self, context) -> None:  # type: ignore[override]
        super().register(context)
        self._checkpoint_manager.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("Trainer checkpoints will be written to %s", self._checkpoint_manager.checkpoint_dir)

    # ------------------------------------------------------------------
    # Public API used by Trainer
    # ------------------------------------------------------------------
    def restore(self, context: ComponentContext) -> None:
        """Load trainer state if checkpoints exist and broadcast to all ranks."""
        payload: Optional[Dict[str, Any]] = None

        if self._distributed.is_master():
            trainable_policy_names = [
                policy_name
                for policy_name, cfg in context.policy_assets.configs.items()
                if cfg.trainable and cfg.optimizer is not None
            ]
            if len(trainable_policy_names) != 1:
                logger.info(
                    "Skipping trainer state restore for %d trainable policies; using recipe defaults.",
                    len(trainable_policy_names),
                )
            else:
                policy_name = trainable_policy_names[0]
                raw = self._checkpoint_manager.load_trainer_state(context.latest_policy_uris.get(policy_name))
                if raw:
                    logger.info(
                        "Restoring trainer state from epoch=%s agent_step=%s", raw.get("epoch"), raw.get("agent_step")
                    )
                    payload = {
                        "agent_step": raw.get("agent_step", 0),
                        "epoch": raw.get("epoch", 0),
                        "avg_reward": raw.get("avg_reward"),
                        "stopwatch_state": raw.get("stopwatch_state"),
                        "curriculum_state": raw.get("curriculum_state"),
                        "loss_states": raw.get("loss_states", {}),
                    }

        payload = self._distributed.broadcast_from_master(payload)
        if payload is None:
            return

        restored_epoch = payload["epoch"]
        context.agent_step = payload["agent_step"]
        context.epoch = restored_epoch
        context.latest_saved_policy_epoch = restored_epoch

        total_agents = int(context.experience.total_agents)
        device = context.experience.device
        default_avg_reward = context.trajectory_isolator.reward_centering_initial_means()
        avg_reward = payload.get("avg_reward")
        if avg_reward is None:
            avg_reward = default_avg_reward
        avg_reward = torch.as_tensor(avg_reward).to(device=device, dtype=torch.float32)
        if avg_reward.numel() == 1:
            avg_reward = torch.broadcast_to(avg_reward, (total_agents,)).clone()
        elif avg_reward.numel() != total_agents:
            raise RuntimeError(f"Restored avg_reward has {avg_reward.numel()} entries; expected {total_agents}.")
        else:
            avg_reward = avg_reward.reshape((total_agents,)).clone()
        context.state.avg_reward = avg_reward

        self._restore_policy_optimizers(context)

        stopwatch_state = payload.get("stopwatch_state")
        context.state.stopwatch_state = stopwatch_state
        wall_time_baseline = 0.0
        if stopwatch_state:
            context.stopwatch.load_state(stopwatch_state, resume_running=True)
            wall_time_baseline = context.stopwatch.get_elapsed()

        curriculum_state = payload.get("curriculum_state")
        context.state.curriculum_state = curriculum_state
        if curriculum_state and context.curriculum is not None:
            context.curriculum.load_state(curriculum_state)
            logger.info("Successfully restored curriculum state")

        loss_states = payload.get("loss_states") or {}
        context.state.loss_states = loss_states
        for name, loss in context.losses.items():
            stored = loss_states.get(name)
            if stored is None:
                continue
            loss.load_state_dict(stored, strict=False)
        context.state.loss_states = {}

        context.timing_baseline = {
            "agent_step": context.agent_step,
            "wall_time": wall_time_baseline,
        }

    def _restore_policy_optimizers(self, context: ComponentContext) -> None:
        configs = context.policy_assets.configs
        policies = context.policy_assets.policies

        optimizer_payload = None
        if self._distributed.is_master():
            optimizer_payload = {}
            latest_uris = context.latest_policy_uris
            for policy_name, cfg in configs.items():
                if not cfg.trainable:
                    continue
                policy_uri = latest_uris.get(policy_name)
                if not policy_uri:
                    continue
                opt_state = self._checkpoint_manager.load_policy_optimizer_state(policy_uri)
                if opt_state:
                    optimizer_payload[policy_name] = opt_state

        optimizer_payload = self._distributed.broadcast_from_master(optimizer_payload)
        if not optimizer_payload:
            return

        for policy_name, opt_state in optimizer_payload.items():
            policy = policies[policy_name]
            optimizer = getattr(policy, "optimizer", None)
            if optimizer is None:
                continue
            try:
                optimizer.load_state_dict(opt_state)
            except (ValueError, KeyError) as exc:  # pragma: no cover
                logger.warning("Failed to load optimizer state for policy[%s]: %s", policy_name, exc)

    # ------------------------------------------------------------------
    # Callback entry-points
    # ------------------------------------------------------------------
    def on_epoch_end(self, epoch: int) -> None:  # type: ignore[override]
        if not self._distributed.should_checkpoint():
            return
        self._save_state()

    def on_training_complete(self) -> None:  # type: ignore[override]
        if not self._distributed.should_checkpoint():
            return

        self._save_state()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _save_state(self) -> None:
        context = self.context

        try:
            context.state.stopwatch_state = context.stopwatch.save_state()
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.debug("Unable to capture stopwatch state: %s", exc)
            context.state.stopwatch_state = None

        context.state.loss_states = {name: loss.state_dict() for name, loss in context.losses.items()}

        # Capture curriculum state
        if context.curriculum is not None:
            context.state.curriculum_state = context.curriculum.get_state()
        else:
            context.state.curriculum_state = None

        self._checkpoint_manager.save_trainer_state(
            context.epoch,
            context.agent_step,
            avg_reward=context.state.avg_reward,
            stopwatch_state=context.state.stopwatch_state,
            curriculum_state=context.state.curriculum_state,
            loss_states=context.state.loss_states,
        )

        # Release references so we do not pin large GPU tensors between checkpoints
        context.state.loss_states = {}
