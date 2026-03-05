#!/bin/bash
set -euo pipefail

NUM_GPUS=${NUM_GPUS:-$(command -v nvidia-smi > /dev/null && nvidia-smi --list-gpus | wc -l || echo 1)}
NUM_NODES=${NUM_NODES:-1}
MASTER_ADDR=${MASTER_ADDR:-localhost}
MASTER_PORT=${MASTER_PORT:-12345}
NODE_INDEX=${NODE_INDEX:-0}

echo "[CONFIG] Training configuration:"
echo "  - GPUs: $NUM_GPUS"
echo "  - Nodes: $NUM_NODES"
echo "  - Master address: $MASTER_ADDR"
echo "  - Master port: $MASTER_PORT"
echo "  - Node index: $NODE_INDEX"
echo "  - Arguments: $*"

export PYTHONUNBUFFERED=1
export PATH="${HOME}/.local/bin:${PATH}"
export PYTHONPATH=${PYTHONPATH:-}:$(pwd)
export PYTHONOPTIMIZE=1
export WANDB_DIR="./wandb"
export DATA_DIR=${DATA_DIR:-./train_dir}

echo "[INFO] Starting training..."

# Start Datadog agent if configured (must be in run phase, not setup, due to SkyPilot subprocess cleanup)
if [[ -n "${METTA_DD_LOG_FILE:-}" ]]; then
  uv run metta install datadog-agent --non-interactive --profile=softmax-docker || true
fi

# The PyPI pufferlib-core wheel is CPU-only; rebuild from source with CUDA.
# This must happen after all uv run/sync calls since they restore the PyPI wheel.
# --no-build-isolation: let the build see the venv's torch.
# PUFFERLIB_BUILD_CUDA=1: compile .cu files even if torch can't see the GPU at build time.
if command -v nvcc > /dev/null 2>&1; then
  echo "Python dependencies installed"
  PUFFERLIB_BUILD_CUDA=1 uv pip install --no-build-isolation --editable packages/pufferlib-core --no-deps
fi

set +e
uv run --no-sync torchrun \
  --nnodes=$NUM_NODES \
  --nproc-per-node=$NUM_GPUS \
  --master-addr=$MASTER_ADDR \
  --master-port=$MASTER_PORT \
  --node-rank=$NODE_INDEX \
  tools/run.py \
  "$@" 2>&1 | tee -a "${METTA_DD_LOG_FILE:-/dev/null}"
EXIT_CODE=${PIPESTATUS[0]}
set -e

if [[ $EXIT_CODE -eq 0 ]]; then
  echo "[SUCCESS] Training completed successfully"
else
  echo "[ERROR] Training failed with exit code $EXIT_CODE" >&2
fi
exit "$EXIT_CODE"
