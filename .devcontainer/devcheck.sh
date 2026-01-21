#!/bin/bash
# Validates that the devcontainer is set up correctly
# Run this inside the container to verify all tools are working

set -u

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

PASS=0
FAIL=0
WARN=0

pass() {
  echo -e "${GREEN}✓${NC} $1"
  ((PASS++))
}

fail() {
  echo -e "${RED}✗${NC} $1"
  ((FAIL++))
}

warn() {
  echo -e "${YELLOW}!${NC} $1"
  ((WARN++))
}

check_command() {
  local cmd=$1
  local name=${2:-$1}
  local version_flag=${3:---version}
  if command -v "$cmd" &> /dev/null; then
    local version
    version=$("$cmd" $version_flag 2>&1 | head -1) || version="(version unknown)"
    pass "$name: $version"
  else
    fail "$name: not found"
  fi
}

check_credential() {
  local path=$1
  local name=$2
  if [ -e "$path" ]; then
    if [ -s "$path" ] || [ -d "$path" ] && [ "$(ls -A "$path" 2> /dev/null)" ]; then
      pass "$name: $path (configured)"
    else
      warn "$name: $path (exists but empty)"
    fi
  else
    warn "$name: $path (not configured)"
  fi
}

echo "========================================"
echo "Metta Devcontainer Validation"
echo "========================================"
echo

# -----------------------------------------------------------------------------
echo "== Environment =="
# -----------------------------------------------------------------------------

if [ "$PWD" = "/workspace" ] || [[ "$PWD" == /workspace/* ]]; then
  pass "Working directory: $PWD"
else
  warn "Working directory: $PWD (expected /workspace)"
fi

if [ -f /workspace/pyproject.toml ]; then
  pass "Workspace mounted: /workspace/pyproject.toml exists"
else
  fail "Workspace mounted: /workspace/pyproject.toml not found"
fi

echo

# -----------------------------------------------------------------------------
echo "== Programming Languages =="
# -----------------------------------------------------------------------------

check_command python Python
check_command node Node.js
check_command rustc Rust
check_command go Go "version"
check_command nim Nim

echo

# -----------------------------------------------------------------------------
echo "== Build Tools =="
# -----------------------------------------------------------------------------

check_command uv uv
check_command bazel Bazel

# Nimble is installed alongside nim but may not be on PATH
if command -v nimble &> /dev/null; then
  check_command nimble Nimble
elif [ -x "/root/.nimby/nim/bin/nimble" ]; then
  version=$(/root/.nimby/nim/bin/nimble --version 2>&1 | head -1)
  pass "Nimble: $version (at /root/.nimby/nim/bin/nimble)"
else
  warn "Nimble: not on PATH (optional)"
fi

# Check if Python venv is active
if [ -n "${VIRTUAL_ENV:-}" ]; then
  pass "Python venv: $VIRTUAL_ENV"
else
  warn "Python venv: not activated"
fi

# Check if dependencies are installed
if python -c "import torch" 2> /dev/null; then
  torch_version=$(python -c "import torch; print(torch.__version__)")
  pass "PyTorch: $torch_version"
else
  fail "PyTorch: not installed (run 'uv sync')"
fi

echo

# -----------------------------------------------------------------------------
echo "== AI Coding Assistants =="
# -----------------------------------------------------------------------------

check_command claude "Claude Code"
check_command codex "OpenAI Codex"

echo

# -----------------------------------------------------------------------------
echo "== Developer Tools =="
# -----------------------------------------------------------------------------

check_command git Git
check_command gh "GitHub CLI"
check_command gt "Graphite CLI"

echo

# -----------------------------------------------------------------------------
echo "== Shells =="
# -----------------------------------------------------------------------------

check_command bash Bash
check_command fish Fish
check_command nu Nushell
check_command starship Starship

echo

# -----------------------------------------------------------------------------
echo "== Credentials (mounted from host) =="
# -----------------------------------------------------------------------------

check_credential ~/.claude "Claude"
check_credential ~/.codex "Codex"
check_credential ~/.config/gh/hosts.yml "GitHub CLI"
check_credential ~/.config/gcloud "Google Cloud"
check_credential ~/.config/wandb "Weights & Biases"
check_credential ~/.netrc ".netrc"
check_credential ~/.sky "SkyPilot"
check_credential ~/.config/graphite "Graphite"
check_credential ~/.config/devdotfiles "Dotfiles"

echo

# -----------------------------------------------------------------------------
echo "== Metta CLI =="
# -----------------------------------------------------------------------------

if command -v metta &> /dev/null; then
  pass "metta: $(which metta)"
else
  # Check if it works via uv run
  if uv run python -m metta.setup.metta_cli --help &> /dev/null; then
    pass "metta: available via 'uv run python -m metta.setup.metta_cli'"
  else
    fail "metta: not available"
  fi
fi

echo

# -----------------------------------------------------------------------------
echo "========================================"
echo "Summary"
echo "========================================"
echo -e "${GREEN}Passed:${NC} $PASS"
echo -e "${RED}Failed:${NC} $FAIL"
echo -e "${YELLOW}Warnings:${NC} $WARN"
echo

if [ $FAIL -gt 0 ]; then
  echo -e "${RED}Some checks failed. Review the output above.${NC}"
  exit 1
elif [ $WARN -gt 0 ]; then
  echo -e "${YELLOW}All required checks passed, but some optional items need attention.${NC}"
  exit 0
else
  echo -e "${GREEN}All checks passed!${NC}"
  exit 0
fi
