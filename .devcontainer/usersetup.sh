#!/bin/bash
set -eu

LOG_FILE="/tmp/usersetup.log"

log() {
  local timestamp
  timestamp=$(date '+%Y-%m-%d %H:%M:%S')
  echo "[$timestamp] $*" | tee -a "$LOG_FILE"
}

log "=== Metta devcontainer usersetup started ==="
log "Hostname: $(hostname)"
log "User: $(whoami)"
log "Working directory: $(pwd)"
# Remove existing venv if it was created on a different platform (e.g., Mac host)
# This ensures scripts have correct shebangs for the container environment
if [ -d ".venv" ]; then
  VENV_PYTHON=".venv/bin/python3"
  if [ -L "$VENV_PYTHON" ] && [ ! -e "$VENV_PYTHON" ]; then
    log "Removing venv with broken Python symlink (likely created on host)"
    rm -rf .venv
  fi
fi

# Sync Python dependencies (increase timeout for large packages like torch)
log "Starting uv sync..."
start_time=$(date +%s)
UV_HTTP_TIMEOUT=300 uv sync --frozen 2>&1 | tee -a "$LOG_FILE"
end_time=$(date +%s)
log "uv sync completed in $((end_time - start_time)) seconds"

# Run dotfiles setup if present (mounted from host ~/.config/devdotfiles)
DOTFILES_DIR="$HOME/.config/devdotfiles"
if [ -d "$DOTFILES_DIR" ]; then
  for script in "$DOTFILES_DIR/setup.sh" "$DOTFILES_DIR/install.sh" "$DOTFILES_DIR/bootstrap.sh"; do
    if [ -x "$script" ]; then
      log "Running dotfiles script: $script"
      "$script" 2>&1 | tee -a "$LOG_FILE"
      break
    elif [ -f "$script" ]; then
      log "Running dotfiles script: $script"
      bash "$script" 2>&1 | tee -a "$LOG_FILE"
      break
    fi
  done
else
  log "No dotfiles found at $DOTFILES_DIR"
fi

log "=== Metta devcontainer usersetup complete ==="
log "Log file saved to: $LOG_FILE"
