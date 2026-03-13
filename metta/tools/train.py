import contextlib
import logging
import math
import multiprocessing
import os
import platform
import re
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from typing import Any, Optional

import torch
from pydantic import Field

from metta.agent.policy import Policy
from metta.agent.util.torch_backends import build_sdpa_context
from metta.app_backend.clients.stats_client import StatsClient
from metta.cogworks.curriculum import Curriculum
from metta.common.tool import Tool
from metta.common.util.heartbeat import record_heartbeat
from metta.common.util.log_config import getRankAwareLogger, init_logging
from metta.common.wandb.context import WandbConfig, WandbContext, WandbRun
from metta.rl.checkpoint_manager import CheckpointManager
from metta.rl.loss.diff_horde import DiffHordeLossConfig
from metta.rl.loss.losses import LossesConfig
from metta.rl.policy_assets import PolicyAssetConfig, PolicyAssetRegistry
from metta.rl.trainer import Trainer
from metta.rl.trainer_config import TorchProfilerConfig, TrainerConfig
from metta.rl.training import (
    Checkpointer,
    CheckpointerConfig,
    ContextCheckpointer,
    DistributedHelper,
    Evaluator,
    EvaluatorConfig,
    GradientReporter,
    GradientReporterConfig,
    Heartbeat,
    Monitor,
    ProgressLogger,
    StatsReporter,
    StatsReporterConfig,
    TorchProfiler,
    TrainerComponent,
    TrainingEnvironmentConfig,
    UpdateEpochAutoTuner,
    VectorizedTrainingEnvironment,
    WandbAborter,
    WandbAborterConfig,
)
from metta.rl.training.batch import calculate_batch_sizes
from metta.rl.training.distributed_helper import distributed_world_size_and_rank_from_env
from metta.rl.training.scheduler import LossScheduler, SchedulerConfig
from metta.rl.training.trajectory_isolation import (
    TrajectoryIsolationConfig,
    TrajectoryIsolationSliceConfig,
    default_trajectory_isolation_config,
)
from metta.sim.simulation_config import SimulationConfig
from metta.tools.utils.auto_config import (
    PolicyStorageDecision,
    auto_policy_storage_decision,
    auto_run_name,
    auto_stats_server_uri,
    auto_wandb_config,
)
from mettagrid.policy.loader import resolve_policy_class_path
from mettagrid.policy.policy import PolicySpec
from mettagrid.util.uri_resolvers.schemes import policy_spec_from_uri, resolve_uri

logger = getRankAwareLogger(__name__)


class TrainTool(Tool):
    run: Optional[str] = None
    initial_policy_uri: Optional[str] = None
    trainer: TrainerConfig = Field(default_factory=TrainerConfig)
    training_env: TrainingEnvironmentConfig
    policy_assets: dict[str, PolicyAssetConfig] = Field(default_factory=lambda: {"learner0": PolicyAssetConfig()})
    losses: LossesConfig | None = None
    trajectory_isolation: TrajectoryIsolationConfig = Field(default_factory=default_trajectory_isolation_config)
    checkpointer: CheckpointerConfig = Field(default_factory=CheckpointerConfig)
    gradient_reporter: GradientReporterConfig = Field(default_factory=GradientReporterConfig)
    stats_server_uri: Optional[str] = auto_stats_server_uri()
    wandb: WandbConfig = WandbConfig.Unconfigured()
    group: Optional[str] = None
    evaluator: EvaluatorConfig = Field(default_factory=EvaluatorConfig)
    torch_profiler: TorchProfilerConfig = Field(default_factory=TorchProfilerConfig)
    scheduler: SchedulerConfig | None = None
    context_checkpointer: dict[str, Any] = Field(default_factory=dict)
    stats_reporter: StatsReporterConfig = Field(default_factory=StatsReporterConfig)
    wandb_aborter: WandbAborterConfig = Field(default_factory=WandbAborterConfig)
    map_preview_uri: str | None = None
    disable_macbook_optimize: bool = False
    sandbox: bool = False

    extra_components: list[Any] = Field(default_factory=list, exclude=True)
    """Additional trainer components to register (e.g., curriculum updaters)."""

    def output_references(self, job_name: str) -> dict:
        storage = auto_policy_storage_decision(job_name)
        policy_uri = storage.remote_prefix or f"file://{self.system.data_dir / job_name / 'checkpoints'}"
        return {"policy_uri": policy_uri}

    def apply_defaults_and_mutations(self, args: dict[str, str]) -> None:
        """Apply TrainTool config defaulting/mutations before running.

        This is intentionally called by `tools/run.py` before `--dry-run`,
        `--print-effective-config`, and `invoke()` so those modes reflect what
        will actually happen at runtime.
        """
        if "run" in args:
            if self.run is not None:
                # Recipe function already consumed run= and configured policy assets;
                # skip the CLI override to avoid double-processing.
                run_from_cli = False
            else:
                self.run = args["run"]
                run_from_cli = True
        else:
            run_from_cli = False

        self._apply_resume_hints()

        if self.run is None:
            self.run = auto_run_name(prefix="local")

        self._finalize_policy_assets(run_from_cli=run_from_cli)
        if run_from_cli and self.group:
            self._validate_sweep_compatibility()

        if self.wandb == WandbConfig.Unconfigured():
            self.wandb = auto_wandb_config(self.run)

        if self.group:
            self.wandb.group = self.group

        if (
            platform.system() == "Darwin"
            and str(self.system.device).startswith("mps")
            and self.training_env.vectorization == "serial"
        ):
            logger.warning("MPS requested on macOS; switching to multiprocessing vectorization.")
            self.training_env.vectorization = "multiprocessing"

        if platform.system() == "Darwin" and not self.disable_macbook_optimize:
            self._minimize_config_for_debugging()  # this overrides many config settings for local testings

        if self.sandbox:
            self._apply_sandbox_config()
            logger.info("Running in sandbox mode (fast validation: 1M steps, epoch-1 checkpoints/evals)")

        # Ensure we checkpoint whenever we evaluate by making checkpointer.epoch_interval
        # a divisor of evaluator.epoch_interval
        if self.evaluator.epoch_interval != 0 and self.evaluator.epoch_interval % self.checkpointer.epoch_interval != 0:
            logger.warning(
                "evaluator.epoch_interval (%d) is not a multiple of checkpointer.epoch_interval (%d). "
                "Adjusting checkpointer.epoch_interval to %d to ensure checkpoints occur during evaluations.",
                self.evaluator.epoch_interval,
                self.checkpointer.epoch_interval,
                self.evaluator.epoch_interval,
            )
            self.checkpointer.epoch_interval = self.evaluator.epoch_interval

        if self.evaluator.evaluate_local:
            # suppress NCCL watchdog timeouts while ranks wait for master to complete evals
            logger.warning("Local policy evaluation can be inefficient - consider switching to remote evaluation!")
            self.system.nccl_timeout = timedelta(hours=4)

        world_size, rank = distributed_world_size_and_rank_from_env(self.system)
        if world_size > 1:
            if self.trainer.scale_batches_by_world_size:
                self.trainer.batch_size = self.trainer.batch_size // world_size
                self.training_env.forward_pass_minibatch_target_size = max(
                    1, self.training_env.forward_pass_minibatch_target_size // world_size
                )
                logger.info(
                    "Scaled batch config for %s processes: batch_size=%s, forward_pass_minibatch_target_size=%s",
                    world_size,
                    self.trainer.batch_size,
                    self.training_env.forward_pass_minibatch_target_size,
                )
            self.training_env.seed += rank

    def _sanitize_checkpoint_namespace(self, value: str) -> str:
        sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")
        return sanitized or "policy"

    def _checkpoint_namespace_for_asset(self, asset: PolicyAssetConfig) -> str:
        if asset.run:
            return asset.run
        if asset.uri:
            try:
                parsed = resolve_uri(asset.uri)
            except ValueError:
                return self._sanitize_checkpoint_namespace(asset.uri)
            if parsed.checkpoint_info:
                return parsed.checkpoint_info[0]
            return self._sanitize_checkpoint_namespace(parsed.canonical)
        raise ValueError("Policy asset must define run or uri to determine checkpoint namespace")

    def _checkpoint_manager_for_asset(
        self,
        base_manager: CheckpointManager,
        asset: PolicyAssetConfig,
    ) -> CheckpointManager:
        try:
            namespace = self._checkpoint_namespace_for_asset(asset)
        except ValueError:
            if not asset.trainable:
                return base_manager
            raise
        if namespace == base_manager.run_name:
            return base_manager
        return CheckpointManager(
            run=namespace,
            system_cfg=self.system,
        )

    def invoke(self, args: dict[str, str]) -> int | None:
        distributed_helper = DistributedHelper(self.system)

        losses_cfg = self.losses or self.trainer.losses
        # Only request per-step env info when a configured loss explicitly needs it. This keeps
        # default training fast (no per-step stats IPC) while preserving diff_horde info_scalar.
        step_info_keys: set[str] = set(self.training_env.step_info_keys)

        for loss_cfg in losses_cfg.losses.values():
            if isinstance(loss_cfg, DiffHordeLossConfig):
                step_info_keys.update(loss_cfg.cumulants.required_info_keys())
        if step_info_keys:
            self.training_env.step_info_keys = tuple(sorted(step_info_keys))

        sup_uri = self.training_env.supervisor_policy_uri
        supervisor_policy_spec: PolicySpec | None = None
        if sup_uri:
            candidate = Path(sup_uri)
            if "://" in sup_uri or candidate.suffix or os.sep in sup_uri or candidate.parent != Path("."):
                supervisor_policy_spec = policy_spec_from_uri(sup_uri)
            else:
                class_path = resolve_policy_class_path(sup_uri)
                supervisor_policy_spec = PolicySpec(class_path=class_path)

        run_name = self.run
        preflight_executor: ThreadPoolExecutor | None = None
        storage_future: Future[PolicyStorageDecision] | None = None
        stats_future: Future[Optional[StatsClient]] | None = None
        storage_decision: PolicyStorageDecision | None = None
        stats_client: Optional[StatsClient] = None
        needs_preflight = not self.system.local_only or (distributed_helper.is_master() and self.stats_server_uri)
        start_method = multiprocessing.get_start_method()
        can_thread_preflight = needs_preflight and (
            self.training_env.vectorization == "serial" or start_method != "fork"
        )
        if can_thread_preflight:
            preflight_executor = ThreadPoolExecutor(max_workers=2)
            if not self.system.local_only:
                storage_future = preflight_executor.submit(auto_policy_storage_decision, run_name)
            if distributed_helper.is_master() and self.stats_server_uri:
                stats_future = preflight_executor.submit(self._maybe_create_stats_client, distributed_helper)

        env = VectorizedTrainingEnvironment(self.training_env, supervisor_policy_spec=supervisor_policy_spec)

        cuda_teacher = None
        if self.training_env.cuda_teacher_policy_uri:
            from metta.rl.training.cuda_teacher import CudaTeacherRunner  # noqa: PLC0415

            cuda_teacher = CudaTeacherRunner(
                policy_uri=self.training_env.cuda_teacher_policy_uri,
                device=torch.device(self.system.device),
                policy_env_info=env.policy_env_info,
            )

        if needs_preflight and not can_thread_preflight:
            if not self.system.local_only:
                storage_decision = auto_policy_storage_decision(run_name)
            if distributed_helper.is_master() and self.stats_server_uri:
                stats_client = self._maybe_create_stats_client(distributed_helper)

        self._configure_torch_backends()

        if storage_future:
            storage_decision = storage_future.result()

        checkpoint_manager = CheckpointManager(
            run=run_name,
            system_cfg=self.system,
            storage_decision=storage_decision,
        )

        init_logging(run_dir=checkpoint_manager.run_dir)
        record_heartbeat()

        # ------------------------------------------------------------------
        # Policy asset registry: load/create all declared policies and add them to the registry.
        # ------------------------------------------------------------------
        loaded_policies: dict[str, Policy] = {}
        for policy_name, asset in self.policy_assets.items():
            asset_checkpoint_manager = self._checkpoint_manager_for_asset(checkpoint_manager, asset)
            loader_checkpointer = Checkpointer(
                config=self.checkpointer,
                checkpoint_manager=asset_checkpoint_manager,
                distributed_helper=distributed_helper,
                policy_architecture=asset.architecture,
                policy_name=policy_name,
            )
            policy_obj = loader_checkpointer.load_or_create_policy(
                env.policy_env_info,
                policy_uri=asset.uri,
            )
            if asset.architecture is None and loader_checkpointer.policy_architecture is not None:
                asset.architecture = loader_checkpointer.policy_architecture

            if not asset.trainable:
                policy_obj.eval()
                for param in policy_obj.parameters():
                    param.requires_grad = False

            loaded_policies[policy_name] = policy_obj

        policy_assets = PolicyAssetRegistry(
            configs=self.policy_assets,
            policies=loaded_policies,
        )

        if distributed_helper.is_master():
            for policy_name, policy in policy_assets.policies.items():
                total_params = sum(param.numel() for param in policy.parameters())
                trainable_params = sum(param.numel() for param in policy.parameters() if param.requires_grad)
                logging.info(
                    "policy[%s] parameters: total=%d trainable=%d",
                    policy_name,
                    total_params,
                    trainable_params,
                )

        # Normalize losses to a single source: self.trainer.losses
        # If self.losses is set, use it; otherwise use self.trainer.losses (which has defaults).
        # The scheduler mutates self.trainer.losses, so we always use that as the source of truth.
        if self.losses is not None:
            self.trainer.losses = self.losses

        trainer = self._initialize_trainer(env, policy_assets, distributed_helper, cuda_teacher=cuda_teacher)

        self._log_run_configuration(distributed_helper, checkpoint_manager, env)

        if stats_future:
            stats_client = stats_future.result()
        elif stats_client is None:
            stats_client = self._maybe_create_stats_client(distributed_helper)

        if preflight_executor is not None:
            preflight_executor.shutdown(wait=False)
        wandb_manager = self._build_wandb_manager(distributed_helper)

        try:
            with wandb_manager as wandb_run:
                self._register_components(
                    trainer=trainer,
                    distributed_helper=distributed_helper,
                    checkpoint_manager=checkpoint_manager,
                    stats_client=stats_client,
                    policy_assets=policy_assets,
                    run_name=self.run,
                    wandb_run=wandb_run,
                )

                trainer.restore()
                trainer.train()

            # Training completed successfully
            return 0

        except KeyboardInterrupt:
            logger.warning("Training interrupted by user")
            return 130  # Standard exit code for Ctrl+C

        except Exception as e:
            logger.error(f"Training failed with exception: {e}", exc_info=True)
            return 1

        finally:
            env.close()
            if stats_client:
                stats_client.close()
            distributed_helper.cleanup()
            sdpa_stack = getattr(self, "_sdpa_context_stack", None)
            if sdpa_stack is not None:
                sdpa_stack.close()
                self._sdpa_context_stack = None

    def _initialize_trainer(
        self,
        env: VectorizedTrainingEnvironment,
        policy_assets: PolicyAssetRegistry,
        distributed_helper: DistributedHelper,
        *,
        cuda_teacher=None,
    ) -> Trainer:
        trainer = Trainer(
            self.trainer,
            env,
            policy_assets=policy_assets,
            losses_cfg=self.trainer.losses,
            trajectory_isolation=self.trajectory_isolation,
            device=torch.device(self.system.device),
            distributed_helper=distributed_helper,
            run_name=self.run,
            cuda_teacher=cuda_teacher,
        )

        if not self.gradient_reporter.epoch_interval and getattr(self.trainer, "grad_mean_variance_interval", 0):
            self.gradient_reporter.epoch_interval = self.stats_reporter.grad_mean_variance_interval

        return trainer

    def _finalize_policy_assets(self, *, run_from_cli: bool) -> None:
        trainable_assets = [
            (name, cfg) for name, cfg in self.policy_assets.items() if cfg.trainable and cfg.optimizer is not None
        ]

        if run_from_cli:
            if len(trainable_assets) != 1:
                raise ValueError(
                    "CLI run is only supported when exactly one trainable policy asset is configured. "
                    "Set run per policy asset for multi-policy training."
                )
            _name, cfg = trainable_assets[0]
            cfg.run = self.run

        if len(trainable_assets) == 1:
            _name, cfg = trainable_assets[0]
            if cfg.run is None and cfg.uri is None:
                cfg.run = self.run

    def _validate_sweep_compatibility(self) -> None:
        trainable_assets = [name for name, cfg in self.policy_assets.items() if cfg.trainable]
        non_trainable_assets = [name for name, cfg in self.policy_assets.items() if not cfg.trainable]

        if non_trainable_assets:
            raise ValueError(
                "Sweeps require all policy assets to be trainable. "
                f"Non-trainable policies configured: {', '.join(non_trainable_assets)}"
            )

        if len(trainable_assets) != 1:
            raise ValueError(
                "Sweeps require exactly one trainable policy asset. "
                f"Found {len(trainable_assets)}: {', '.join(trainable_assets) or 'none'}"
            )

        trainable_policy = trainable_assets[0]
        slices = self.trajectory_isolation.slices
        if len(slices) != 1:
            raise ValueError(f"Sweeps require exactly one trajectory isolation slice. Found {len(slices)} slices.")

        slice_cfg: TrajectoryIsolationSliceConfig = slices[0]
        if not math.isclose(slice_cfg.env_ratio, 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise ValueError(
                f"Sweeps require a single monolithic slice with env_ratio=1.0. Found env_ratio={slice_cfg.env_ratio}."
            )
        if slice_cfg.policies != [trainable_policy]:
            raise ValueError(
                "Sweeps require the trajectory slice policies to contain only the trainable policy. "
                f"Found policies={slice_cfg.policies}."
            )
        if slice_cfg.primary_policy != trainable_policy:
            raise ValueError(
                "Sweeps require the trajectory slice primary_policy to match the trainable policy. "
                f"Found primary_policy={slice_cfg.primary_policy}."
            )

    def _apply_resume_hints(self) -> None:
        if not self.initial_policy_uri:
            return
        try:
            parsed = resolve_uri(self.initial_policy_uri)
        except ValueError as exc:
            logger.debug("Skipping resume hints for %s: %s", self.initial_policy_uri, exc)
            return
        if parsed.scheme == "mock" or not parsed.checkpoint_info or self.run is not None:
            return
        self.run = parsed.checkpoint_info[0]

        trainer_state_path = self.system.data_dir / self.run / "checkpoints" / "trainer_state.pt"
        if trainer_state_path.exists():
            logger.info("Trainer state found at %s; optimizer/curriculum state will be restored.", trainer_state_path)

    def _register_components(
        self,
        *,
        trainer: Trainer,
        distributed_helper: DistributedHelper,
        checkpoint_manager: CheckpointManager,
        stats_client: Optional[StatsClient],
        policy_assets: PolicyAssetRegistry,
        run_name: str,
        wandb_run: WandbRun | None,
    ) -> None:
        components: list[TrainerComponent] = []

        heartbeat_cfg = getattr(self.trainer, "heartbeat", None)
        if heartbeat_cfg is not None:
            components.append(Heartbeat(epoch_interval=heartbeat_cfg.epoch_interval))

        autotune_cfg = getattr(self.trainer, "update_epochs_autotune", None)
        if autotune_cfg and getattr(autotune_cfg, "enabled", False):
            components.append(UpdateEpochAutoTuner(autotune_cfg))

        if distributed_helper.is_master():
            stats_config = self.stats_reporter.model_copy(update={"report_to_wandb": bool(wandb_run)})
            reporting_enabled = stats_config.report_to_wandb or stats_config.report_to_console

            if self.gradient_reporter.epoch_interval:
                components.append(GradientReporter(self.gradient_reporter))

            stats_component = StatsReporter.from_config(
                stats_config,
                wandb_run=wandb_run,
            )
            components.append(stats_component)

            # Register per-policy checkpointers for policies that request checkpointing.
            for policy_name, asset in policy_assets.configs.items():
                if not asset.checkpoint:
                    continue
                asset_checkpoint_manager = self._checkpoint_manager_for_asset(checkpoint_manager, asset)
                components.append(
                    Checkpointer(
                        config=self.checkpointer,
                        checkpoint_manager=asset_checkpoint_manager,
                        distributed_helper=distributed_helper,
                        policy_architecture=asset.architecture,
                        policy_getter=lambda name=policy_name: policy_assets.get(name),
                        policy_name=policy_name,
                    )
                )

            self.evaluator = self.evaluator.model_copy(deep=True)
            components.append(
                Evaluator(
                    config=self.evaluator,
                    device=torch.device(self.system.device),
                    seed=self.system.seed,
                    run_name=run_name,
                    stats_client=stats_client,
                    wandb_run=wandb_run,
                )
            )

            components.append(Monitor(enabled=reporting_enabled))
            components.append(ProgressLogger())

        if self.context_checkpointer:
            logger.debug(
                "Context checkpointer configuration is ignored; checkpointing is policy-driven now: %s",
                self.context_checkpointer,
            )

        components.append(
            ContextCheckpointer(
                checkpoint_manager=checkpoint_manager,
                distributed_helper=distributed_helper,
                epoch_interval=max(1, self.checkpointer.epoch_interval),
            )
        )
        components.append(WandbAborter(wandb_run=wandb_run, config=self.wandb_aborter))

        if distributed_helper.is_master() and getattr(self.torch_profiler, "interval_epochs", 0):
            components.append(
                TorchProfiler(
                    profiler_config=self.torch_profiler,
                    wandb_run=wandb_run,
                    run_dir=checkpoint_manager.run_dir,
                    is_master=True,
                )
            )

        for component in components:
            trainer.register(component)

        for component in self.extra_components:
            trainer.register(component)

        for component in self.training_env.curriculum.get_trainer_components():
            trainer.register(component)

        if self.scheduler is not None:
            trainer.register(LossScheduler(self.scheduler))

    def _configure_torch_backends(self) -> None:
        if not torch.cuda.is_available():
            return

        # Opportunistically enable flash attention when available
        if os.environ.get("FLASH_ATTENTION") is None:
            try:
                import flash_attn  # noqa: F401, PLC0415
            except ImportError:
                pass
            else:
                os.environ["FLASH_ATTENTION"] = "1"

        context = build_sdpa_context(
            prefer_flash=True,
            prefer_mem_efficient=True,
            prefer_math=True,
            set_priority=True,
        )
        if context is not None:
            stack = getattr(self, "_sdpa_context_stack", None)
            if stack is None:
                stack = contextlib.ExitStack()
                self._sdpa_context_stack = stack
            stack.enter_context(context)

    def _log_run_configuration(
        self,
        distributed_helper: DistributedHelper,
        checkpoint_manager: CheckpointManager,
        env: VectorizedTrainingEnvironment,
    ) -> None:
        if not distributed_helper.is_master():
            return

        if not checkpoint_manager.run_dir:
            raise ValueError("cannot _log_run_configuration without a valid run_dir")

        logger.info(f"Training environment: {env}")
        config_path = os.path.join(checkpoint_manager.run_dir, "config.json")
        with open(config_path, "w") as config_file:
            config_file.write(self.model_dump_json(indent=2))
        logger.info(f"Config saved to {config_path}")

    def _maybe_create_stats_client(self, distributed_helper: DistributedHelper) -> Optional[StatsClient]:
        if not (distributed_helper.is_master() and self.stats_server_uri):
            return None
        try:
            return StatsClient.create(stats_server_uri=self.stats_server_uri)

        except Exception as exc:
            logger.warning("Failed to initialize stats client: %s", exc)
            return None

    def _build_wandb_manager(self, distributed_helper: DistributedHelper):
        if distributed_helper.is_master() and self.wandb.enabled:
            return WandbContext(self.wandb, self)
        return contextlib.nullcontext(None)

    def _minimize_config_for_debugging(self) -> None:
        self.trainer.bptt_horizon = min(self.trainer.bptt_horizon, 8)

        self.training_env.async_factor = 1
        self.training_env.forward_pass_minibatch_target_size = min(
            self.training_env.forward_pass_minibatch_target_size, 4
        )

        env_cfg = Curriculum(self.training_env.curriculum).get_task().get_env_cfg()
        num_agents = int(env_cfg.game.num_agents)
        num_workers = self.training_env.num_workers
        if self.training_env.vectorization == "serial":
            num_workers = 1

        _, _, num_envs = calculate_batch_sizes(
            forward_pass_minibatch_target_size=self.training_env.forward_pass_minibatch_target_size,
            num_agents=num_agents,
            num_workers=num_workers,
            async_factor=self.training_env.async_factor,
        )
        expected_batch_size = num_envs * num_agents * self.trainer.bptt_horizon

        self.trainer = self.trainer.model_copy(
            update={
                "batch_size": expected_batch_size,
                "minibatch_size": expected_batch_size,
            }
        )

        self.checkpointer.epoch_interval = min(self.checkpointer.epoch_interval, 10)
        self.evaluator.epoch_interval = min(self.evaluator.epoch_interval, 10)

    def _apply_sandbox_config(self) -> None:
        """Apply sandbox mode configuration for fast validation testing."""
        # Reduce total timesteps for very quick testing (1M instead of 50B)
        self.trainer.total_timesteps = 1_000_000

        # Save checkpoint after first epoch
        self.checkpointer.epoch_interval = 1

        # Run evaluation after first epoch with short episodes for fast validation
        self.evaluator.epoch_interval = 1
        self.evaluator.allow_eval_without_stats = True

        # Create a short evaluation environment (100 steps instead of 1000+)
        # This makes evaluations complete in ~10-20 seconds instead of minutes
        curriculum = Curriculum(self.training_env.curriculum)
        eval_env = curriculum.get_task().get_env_cfg().model_copy(deep=True)
        eval_env.game.max_steps = 100

        self.evaluator.training_replay_envs = [
            SimulationConfig(
                suite="training",
                name="sandbox_validation",
                env=eval_env,
            )
        ]
        # Clear any additional simulations - only run the quick training validation
        self.evaluator.simulations = []
