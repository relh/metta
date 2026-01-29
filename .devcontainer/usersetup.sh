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

# Rebuild mettagrid_c.so for Linux
# The workspace is mounted from the host, so if developed on Mac, the .so file
# will be a Mach-O binary that won't work in the Linux container. We need to
# rebuild it for the container's architecture.
METTAGRID_SO="/workspace/packages/mettagrid/python/src/mettagrid/mettagrid_c.so"
METTAGRID_DIR="/workspace/packages/mettagrid"
if [ -d "$METTAGRID_DIR" ]; then
  # Check if .so exists and is not a Linux ELF binary
  NEEDS_REBUILD=false
  if [ ! -f "$METTAGRID_SO" ]; then
    NEEDS_REBUILD=true
    log "mettagrid_c.so not found, will build"
  elif ! head -c 4 "$METTAGRID_SO" | grep -q "ELF"; then
    NEEDS_REBUILD=true
    log "mettagrid_c.so is not an ELF binary (likely Mac), will rebuild"
  fi

  if [ "$NEEDS_REBUILD" = true ]; then
    log "Building mettagrid_c.so for Linux..."
    start_time=$(date +%s)
    cd "$METTAGRID_DIR"
    if bazel build //:mettagrid_c 2>&1 | tee -a "$LOG_FILE"; then
      cp bazel-bin/cpp/mettagrid_c.so "$METTAGRID_SO"
      end_time=$(date +%s)
      log "mettagrid_c.so built in $((end_time - start_time)) seconds"
    else
      log "WARNING: Failed to build mettagrid_c.so - some features may not work"
    fi
    cd /workspace
  else
    log "mettagrid_c.so is already a Linux binary, skipping rebuild"
  fi
fi

# Install Nim packages for mettascope.
# The bootstrap process installs nimby (Nim package manager) and nim, but not the
# project-specific packages like opengl, fidget2, boxy, etc. that mettascope depends on.
# These are defined in nimby.lock and installed to ~/.nimby/pkgs/. Without this step,
# `metta nimtest` fails with "cannot open file: opengl" because nim can't find the packages.
METTASCOPE_DIR="/workspace/packages/mettagrid/nim/mettascope"
if [ -d "$METTASCOPE_DIR" ] && command -v nimby &> /dev/null; then
  log "Installing Nim packages for mettascope..."
  cd "$METTASCOPE_DIR"
  nimby sync -g nimby.lock 2>&1 | tee -a "$LOG_FILE"
  cd /workspace
  log "Nim packages installed"
else
  log "Skipping Nim package installation (nimby not found or mettascope dir missing)"
fi

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
