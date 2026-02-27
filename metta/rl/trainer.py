import importlib
from typing import Any, Callable, Iterable, Optional

import torch
from torchrl.data import Composite

from metta.common.util.log_config import getRankAwareLogger
from metta.rl.loss.losses import LossesConfig
from metta.rl.policy_assets import PolicyAssetRegistry
from metta.rl.system_config import SystemConfig
from metta.rl.trainer_config import TrainerConfig
from metta.rl.training import (
    ComponentContext,
    ContextCheckpointer,
    CoreTrainingLoop,
    DistributedHelper,
    Experience,
    TrainerCallback,
    TrainerComponent,
    TrainerState,
    TrainingEnvironment,
)
from metta.rl.training.optimizer import create_optimizer, is_schedulefree_optimizer
from metta.rl.training.trajectory_isolation import TrajectoryIsolationConfig, TrajectoryIsolator
from mettagrid.profiling.stopwatch import Stopwatch

logger = getRankAwareLogger(__name__)


class Trainer:
    """Main trainer facade that coordinates all training components."""

    def __init__(
        self,
        cfg: TrainerConfig,
        env: TrainingEnvironment,
        *,
        policy_assets: PolicyAssetRegistry,
        losses_cfg: Any,
        trajectory_isolation: TrajectoryIsolationConfig,
        device: torch.device,
        distributed_helper: Optional[DistributedHelper] = None,
        run_name: Optional[str] = None,
        cuda_teacher=None,
    ):
        """Initialize trainer with all components.

        Args:
            cfg: Trainer configuration
            env: TrainingEnvironment instance for experience generation
            distributed_helper: Optional helper managing torch.distributed lifecycle
        """
        self._env = env
        self._policy_assets = policy_assets
        self._cfg = cfg
        self._trajectory_isolation = trajectory_isolation
        self._device = device
        try:
            importlib.import_module("pufferlib._C")
        except ImportError:
            raise ImportError("Failed to import C/CUDA kernel. Try: pip install --no-build-isolation") from None
        if self._cfg.detect_anomaly:
            torch.autograd.set_detect_anomaly(True)
            logger.warning("Torch autograd anomaly detection enabled; backward will be slower.")
        if distributed_helper is None:
            distributed_helper = DistributedHelper(SystemConfig(device=self._device.type))
        self._distributed_helper = distributed_helper
        self._run_name = run_name
        self._components: list[TrainerComponent] = []
        self.timer = Stopwatch(log_level=logger.getEffectiveLevel())
        self.timer.start()

        if isinstance(losses_cfg, LossesConfig):
            losses_cfg.configure_for_policy_env(
                policy_env_info=self._env.policy_env_info,
                trajectory_isolation=self._trajectory_isolation,
            )

        # Initialize all policy assets (trainable and non-trainable) but only wrap if trainable.
        for name, pol in list(policy_assets.policies.items()):
            asset_cfg = policy_assets.get_config(name)
            pol.to(self._device)
            pol.initialize_to_environment(self._env.policy_env_info, self._device)
            # If the policy was frozen upstream, keep it in eval mode.
            if any(p.requires_grad for p in pol.parameters()):
                pol.train()
            else:
                pol.eval()

            if not asset_cfg.trainable:
                policy_assets.policies[name] = pol
            else:
                wrapped = self._distributed_helper.wrap_policy(pol, self._device)
                # TODO: remove wrapped policy assets if they stop being used in losses.
                policy_assets.policies[name] = wrapped

        # Create an optimizer per trainable policy and attach it to the policy instance.
        for name, pol in self._policy_assets.policies.items():
            asset_cfg = self._policy_assets.get_config(name)
            optimizer_cfg = getattr(asset_cfg, "optimizer", None)
            if not asset_cfg.trainable:
                continue
            if optimizer_cfg is None:
                raise ValueError(f"policy_assets['{name}'] is trainable=True but optimizer=None")
            if not any(p.requires_grad for p in pol.parameters()):
                raise ValueError(
                    f"policy_assets['{name}'] is trainable=True but the policy has no parameters with "
                    "requires_grad=True"
                )

            optimizer = create_optimizer(optimizer_cfg, pol)
            pol.optimizer = optimizer

        losses = {
            loss_name: loss_cfg.create(policy_assets, self._cfg, self._env, self._device, loss_name)
            for loss_name, loss_cfg in losses_cfg.losses.items()
        }

        for pol in self._policy_assets.policies.values():
            if any(p.requires_grad for p in pol.parameters()):
                pol.train()
            else:
                pol.eval()

        # Merge all trainable policy experience specs so Experience knows about every key
        # that might be produced during rollout/training, regardless of which policy is active.
        def _merge_policy_specs(specs: list[Composite]) -> Composite:
            merged: dict = {}
            for spec in specs:
                for key, value in spec.items():
                    if key in merged:
                        existing = merged[key]
                        if (
                            getattr(existing, "shape", None) != getattr(value, "shape", None)
                            or getattr(existing, "dtype", None) != getattr(value, "dtype", None)
                            or type(existing) is not type(value)
                        ):
                            raise ValueError(
                                f"Conflicting policy experience specs for key {key!r}: existing={existing} new={value}"
                            )
                    merged[key] = value
            return Composite(merged)

        trainable_policy_specs = [
            pol.get_agent_experience_spec()
            for name, pol in self._policy_assets.policies.items()
            if self._policy_assets.get_config(name).trainable
        ]
        if not trainable_policy_specs:
            raise ValueError("No trainable policies in policy_assets; cannot build experience buffer.")
        merged_policy_spec = _merge_policy_specs(trainable_policy_specs)

        batch_info = self._env.batch_info

        parallel_agents = getattr(self._env, "total_parallel_agents", None)
        if parallel_agents is None:
            parallel_agents = batch_info.num_envs * self._env.policy_env_info.num_agents

        self._experience = Experience.from_losses(
            total_agents=parallel_agents,
            batch_size=self._cfg.batch_size,
            bptt_horizon=self._cfg.bptt_horizon,
            minibatch_size=self._cfg.minibatch_size,
            max_minibatch_size=self._cfg.minibatch_size,
            policy_experience_spec=merged_policy_spec,
            losses=losses,
            device=self._device,
        )

        self._state = TrainerState()
        self._state.avg_reward = torch.full(
            (parallel_agents,),
            0.0,  # TODO: the code doesn't yet resolve which slice the reward centering should come from
            device=self._device,
            dtype=torch.float32,
        )

        # Extract curriculum from environment if available
        curriculum = getattr(self._env, "_curriculum", None)

        self._train_epoch_callable: Callable[[], None] = self._run_epoch

        self._context = ComponentContext(
            state=self._state,
            policy_assets=policy_assets,
            device=self._device,
            env=self._env,
            experience=self._experience,
            config=self._cfg,
            stopwatch=self.timer,
            distributed=self._distributed_helper,
            get_train_epoch_fn=lambda: self._train_epoch_callable,
            set_train_epoch_fn=self._set_train_epoch_callable,
            run_name=self._run_name,
            curriculum=curriculum,
        )
        self._context.policy_assets = policy_assets

        # Validate trajectory isolation references once all inputs exist.
        # This is cross-object validation: slice policy/loss names must exist in the policy registry / losses config.
        self._trajectory_isolation.validate_references(policy_assets=policy_assets.configs, losses=losses_cfg)

        trajectory_isolator = TrajectoryIsolator(config=self._trajectory_isolation)
        self.register(trajectory_isolator)
        self._state.avg_reward = trajectory_isolator.reward_centering_initial_means()

        self.core_loop = CoreTrainingLoop(
            experience=self._experience,
            losses=losses,
            device=self._device,
            context=self._context,
            trajectory_isolator=trajectory_isolator,
            cuda_teacher=cuda_teacher,
        )

        self._losses = losses
        self._context.losses = losses

        for loss in losses.values():
            loss.attach_context(self._context)

        self._prev_agent_step_for_step_callbacks: int = 0

    @property
    def context(self) -> ComponentContext:
        """Return the shared trainer context."""

        return self._context

    def train(self) -> None:
        """Run the main training loop."""

        try:
            while self._state.agent_step < self._cfg.total_timesteps:
                self._train_epoch_callable()

        except Exception:
            self._invoke_callback(TrainerCallback.FAILURE)
            raise

        self._distributed_helper.synchronize()
        self._invoke_callback(TrainerCallback.TRAINING_COMPLETE)

    def _set_train_epoch_callable(self, fn: Callable[[], None]) -> None:
        self._train_epoch_callable = fn

    def _run_epoch(self) -> None:
        """Run a single training epoch."""
        self._context.reset_for_epoch()

        # Start new epoch
        self.core_loop.on_epoch_start(self._context)

        # Rollout phase
        with self.timer("_rollout"):
            # Ensure ScheduleFree optimizer is in eval mode during rollout
            for optimizer in self._iter_schedulefree_optimizers():
                optimizer.eval()

            rollout_result = self.core_loop.rollout_phase(self._env, self._context)
            self._context.training_env_id = rollout_result.training_env_id
            world_size = self._distributed_helper.get_world_size()
            previous_agent_step = self._context.agent_step
            if rollout_result.agent_steps:
                self._context.record_rollout(rollout_result.agent_steps, world_size)
            if rollout_result.raw_infos:
                self._prev_agent_step_for_step_callbacks = previous_agent_step
                self._invoke_callback(TrainerCallback.STEP, rollout_result.raw_infos)
            self._invoke_callback(TrainerCallback.ROLLOUT_END)

        # Training phase
        with self.timer("_train"):
            # ScheduleFree optimizer is in train mode for training phase
            for optimizer in self._iter_schedulefree_optimizers():
                optimizer.train()

            losses_stats, epochs_trained = self.core_loop.training_phase(
                context=self._context,
                update_epochs=self._cfg.update_epochs,
                max_grad_norm=0.5,
            )
            if self._device.type == "cuda":
                # Ensure train-time measurements include queued CUDA work.
                torch.cuda.synchronize()
            self._context.advance_epoch(epochs_trained)
        # Synchronize before proceeding
        self._distributed_helper.synchronize()

        # Store losses stats for callbacks
        self._context.latest_losses_stats = losses_stats

        # Invoke callbacks for epoch end on every rank. Components that should
        # only run on the master process must set `_master_only` so they aren't
        # registered on other ranks.
        self._invoke_callback(TrainerCallback.EPOCH_END)

    def _iter_schedulefree_optimizers(self) -> Iterable[torch.optim.Optimizer]:
        for policy in self._policy_assets.policies.values():
            optimizer = getattr(policy, "optimizer", None)
            if optimizer is not None and is_schedulefree_optimizer(optimizer):
                yield optimizer

    def register(self, component: TrainerComponent) -> None:
        """Register a training component.

        Args:
            component: Training component to register
        """
        if component._master_only and not self._distributed_helper.is_master():
            return

        self._components.append(component)
        component.register(self._context)

    def _invoke_callback(self, callback_type: TrainerCallback, infos: Optional[list[dict[str, Any]]] = None) -> None:
        """Invoke all registered callbacks of the specified type.

        Args:
            callback_type: The type of callback to invoke
            infos: Step information from environment (only used for STEP callback)
        """
        current_step = self._context.agent_step
        previous_step = getattr(self, "_prev_agent_step_for_step_callbacks", current_step)
        current_epoch = self._context.epoch

        for component in self._components:
            try:
                if callback_type == TrainerCallback.STEP:
                    if (
                        component.should_handle_step(current_step=current_step, previous_step=previous_step)
                        and infos is not None
                    ):
                        component.on_step(infos)
                elif callback_type == TrainerCallback.EPOCH_END:
                    if component.should_handle_epoch(current_epoch):
                        component.on_epoch_end(current_epoch)
                elif callback_type == TrainerCallback.ROLLOUT_END:
                    component.on_rollout_end()
                elif callback_type == TrainerCallback.TRAINING_COMPLETE:
                    component.on_training_complete()
                elif callback_type == TrainerCallback.FAILURE:
                    component.on_failure()
            except Exception as e:
                logger.error(
                    f"Component {component.__class__.__name__} {callback_type.value} callback failed: {e}",
                    exc_info=True,
                )

    def restore(self) -> None:
        """Restore trainer state from checkpoints.

        This should be called after setup() to restore any saved state.
        """
        for component in self._components:
            if isinstance(component, ContextCheckpointer):
                component.restore(self._context)
                break
            # Wandb setup will be handled by callbacks if configured
