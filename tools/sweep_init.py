#!/usr/bin/env -S uv run

# NumPy 2.0 compatibility for WandB - must be imported before wandb
import numpy as np  # noqa: E402

if not hasattr(np, "byte"):
    np.byte = np.int8

import os
import random
import sys
import time
from logging import Logger

import hydra
import wandb
from omegaconf import DictConfig, ListConfig, OmegaConf

from metta.common.util.lock import run_once
from metta.common.util.logging_helpers import setup_mettagrid_logger
from metta.common.util.numpy_helpers import clean_numpy_types
from metta.common.util.retry import retry_on_exception
from metta.common.util.script_decorators import metta_script
from metta.common.wandb.wandb_context import WandbContext
from metta.sweep.protein_metta import MettaProtein
from metta.sweep.wandb_utils import create_wandb_sweep, generate_run_id_for_sweep, sweep_id_from_name

logger = setup_mettagrid_logger("sweep_init")


@hydra.main(config_path="../configs", config_name="sweep_job", version_base=None)
@metta_script
def main(cfg: DictConfig | ListConfig) -> int:
    # Extract sweep base name from CLI sweep_run parameter (e.g., "simple_sweep")
    # Individual training runs will be "simple_sweep.r.0", etc.

    cfg.wandb.name = cfg.sweep_run

    is_master = os.environ.get("NODE_INDEX", "0") == "0"

    run_once(lambda: create_sweep(cfg, logger))

    if is_master:
        create_run(cfg, logger)
    else:
        wait_for_run(cfg, cfg.dist_cfg_path, logger)

    return 0


def create_sweep(cfg: DictConfig | ListConfig, logger: Logger) -> None:
    """
    Create a new sweep with the given name. If the sweep already exists, skip creation.
    Save the sweep configuration to sweep_dir/config.yaml.
    """

    # Check if sweep already exists
    sweep_id = sweep_id_from_name(cfg.wandb.project, cfg.wandb.entity, cfg.sweep_run)
    if sweep_id is not None:
        logger.info(f"Sweep already exists, skipping creation for: {cfg.sweep_run}")
        return

    logger.info(f"Creating new sweep: {cfg.sweep_dir}")
    os.makedirs(cfg.runs_dir, exist_ok=True)

    # Create sweep using static methods from protein_wandb (Protein will control all parameters)
    sweep_id = create_wandb_sweep(cfg.sweep_run, cfg.wandb.entity, cfg.wandb.project)
    OmegaConf.save(
        {
            "sweep": cfg.sweep_run,
            "sweep_run": cfg.sweep_run,  # Add explicit sweep_run field
            "wandb_sweep_id": sweep_id,
            "wandb_path": f"{cfg.wandb.entity}/{cfg.wandb.project}/{sweep_id}",
        },
        os.path.join(cfg.sweep_dir, "config.yaml"),
    )


def create_run(cfg: DictConfig | ListConfig, logger: Logger) -> str:
    """
    Create a new run for an existing sweep.
    Returns the run ID.
    """
    # Load wandb sweep metadata
    sweep_metadata = OmegaConf.load(os.path.join(cfg.sweep_dir, "config.yaml"))

    # Generate a new run ID for the sweep, e.g. "simple_sweep.r.0"
    # TODO: Use sweep_id instead of sweep_path, currently very confusing.
    run_id = generate_run_id_for_sweep(sweep_metadata.wandb_path, cfg.runs_dir)
    logger.info(f"Creating new run: {run_id}")

    run_dir = os.path.join(cfg.runs_dir, run_id)
    os.makedirs(run_dir, exist_ok=True)
    cfg.run = run_id  # Top-level for training scripts
    cfg.run_dir = run_dir  # Top-level for training scripts

    # Set Wandb config values explicitly so they contain concrete strings
    # rather than unresolved interpolations when validated by Pydantic.
    cfg.wandb.group = cfg.sweep_run
    cfg.wandb.name = run_id
    cfg.wandb.run_id = run_id  # Required by WandbConfigOn schema

    def init_run():
        with WandbContext(cfg.wandb, cfg) as wandb_run:
            assert wandb_run, "Wandb should be enabled"
            wandb_run_id = wandb_run.id
            wandb_run.name = run_id
            if not wandb_run.tags:
                wandb_run.tags = ()
            wandb_run.tags += (f"sweep_id:{sweep_metadata.wandb_sweep_id}", f"sweep_run:{sweep_metadata.sweep_run}")

            protein = MettaProtein(cfg.sweep, wandb_run)
            logger.info(f"Protein loaded {getattr(protein, '_num_observations', 0)} previous observations")

            # Suggestions are generated by protein using previous, saved observations.
            # Protein may fail to generate a valid suggestion, in which case it will raise an exception.
            # generate_protein_suggestion will retry up to 10 times, and record failures to the protein.
            try:
                clean_suggestion = generate_protein_suggestion(cfg.sweep_job, protein)
            except Exception as e:
                logger.warning("Failed to generate protein suggestion after 10 attempts. Giving up.")
                raise e

            # Apply Protein suggestions on top of sweep_job overrides
            # Make a deepcopy of the sweep_job config to avoid modifying the original. We need
            # to add the newly generated run-id into the subtree so that ${run} interpolations
            # can resolve, but `cfg.sweep_job` is in struct mode, which forbids adding keys.
            # Temporarily relax struct, insert the value, then restore the original safety.
            OmegaConf.set_struct(cfg.sweep_job, False)
            cfg.sweep_job.run = cfg.run
            OmegaConf.set_struct(cfg.sweep_job, True)
            sweep_job_container = OmegaConf.to_container(cfg.sweep_job, resolve=True)
            assert isinstance(sweep_job_container, dict), "sweep_job must be a dictionary structure"
            sweep_job_copy = DictConfig(sweep_job_container)
            apply_protein_suggestion(sweep_job_copy, clean_suggestion)
            save_path = os.path.join(run_dir, "train_config_overrides.yaml")
            run_seed = random.randint(0, 2**31 - 1)

            # Save the merged config that will be used for training
            # This mimics train_job.yaml
            sweep_job_final = OmegaConf.to_container(sweep_job_copy, resolve=True)
            assert isinstance(sweep_job_final, dict), "sweep_job_final must be a dictionary"
            train_cfg_overrides = DictConfig(
                {
                    **sweep_job_final,
                    "run": run_id,
                    "run_dir": run_dir,
                    "seed": run_seed,
                    "sweep_run": cfg.sweep_run,  # Needed by sweep_eval.py
                    "device": cfg.device,  # Ensure device is at top level
                    "wandb": {
                        "group": cfg.sweep_run,  # Group all runs under the sweep name
                        "name": run_id,  # Individual run name
                    },
                }
            )
            OmegaConf.save(train_cfg_overrides, save_path)

            os.makedirs(os.path.dirname(cfg.dist_cfg_path), exist_ok=True)
            OmegaConf.save(
                {
                    "run": run_id,
                    "wandb_run_id": wandb_run_id,
                },
                cfg.dist_cfg_path,
            )

    wandb.agent(
        sweep_metadata.wandb_sweep_id,
        entity=cfg.wandb.entity,
        project=cfg.wandb.project,
        function=init_run,
        count=1,
    )

    logger.info(f"Run created: {run_id}")
    return run_id


def wait_for_run(cfg: DictConfig | ListConfig, path: str, logger: Logger) -> None:
    """
    Wait for a run to exist.
    """
    for _ in range(10):
        if os.path.exists(path):
            break
        time.sleep(5)

    run_id = OmegaConf.load(path).run
    logger.info(f"Run read: {run_id}")


def validate_protein_suggestion(config: DictConfig, suggestion: dict):
    """Validate a protein suggestion.
    We only validate constraints related total_timesteps, batch_size, minibatch_size, bppt.
    We must have: minibatch_size divides batch_size, bppt divides minibatch_size.

    Args:
        suggestion: The suggestion to validate
    """
    # Parse the config values first
    config_values = OmegaConf.to_container(config, resolve=True)
    assert isinstance(config_values, dict), "config must be a dictionary"

    # Try nested structure first, then flat structure
    trainer_config = config_values["trainer"]
    batch_size = trainer_config.get("batch_size")
    minibatch_size = trainer_config.get("minibatch_size")
    bppt = trainer_config.get("bptt_horizon")

    # Parse the protein suggestion
    if "trainer" in suggestion:
        if "batch_size" in suggestion["trainer"]:
            batch_size = suggestion["trainer"]["batch_size"]
        if "minibatch_size" in suggestion["trainer"]:
            minibatch_size = suggestion["trainer"]["minibatch_size"]
        if "bptt_horizon" in suggestion["trainer"]:
            bppt = suggestion["trainer"]["bptt_horizon"]

    # Validate the suggestion
    if batch_size is not None and minibatch_size is not None and batch_size % minibatch_size != 0:
        raise ValueError(f"Batch size {batch_size} must be divisible by minibatch size {minibatch_size}")
    if minibatch_size is not None and bppt is not None and minibatch_size % bppt != 0:
        raise ValueError(f"Minibatch size {minibatch_size} must be divisible by bppt {bppt}")


@retry_on_exception(max_retries=10, retry_delay=0.1, exceptions=(ValueError,))
def generate_protein_suggestion(config: DictConfig, protein: MettaProtein):
    """Generate a protein suggestion."""
    suggestion, _ = protein.suggest()
    logger.info(f"Protein suggestion: {suggestion}")
    try:
        validate_protein_suggestion(config, suggestion)
    except Exception as e:
        # Catch the invalid exception and record it so Protein can learn from it
        logger.warning(f"Invalid suggestion: {e}")
        protein.record_failure(str(e))
        raise e
    return clean_numpy_types(suggestion)


def apply_protein_suggestion(config: DictConfig, suggestion: dict):
    """Apply suggestions to a configuration object using deep merge.

    Args:
        config: The configuration object to modify (must be a DictConfig)
        suggestion: The suggestions to apply (cleaned dict)
    """
    for key, value in suggestion.items():
        if key == "suggestion_uuid":
            continue

        # Clean numpy types from the value before applying
        cleaned_value = clean_numpy_types(value)

        # For nested structures, merge instead of overwrite
        if key in config and isinstance(config[key], DictConfig) and isinstance(cleaned_value, dict):
            config[key] = OmegaConf.merge(config[key], cleaned_value)
        else:
            config[key] = cleaned_value


if __name__ == "__main__":
    sys.exit(main())
