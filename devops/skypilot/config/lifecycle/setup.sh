#!/usr/bin/env bash

set -eu
REPO_DIR="/workspace/metta"
DEPLOY_KEY_SECRET="github/metta-deploy-key"
AWS_CLI_PATH=""

# Ensure AWS CLI v2 is present (install on-demand for AMI-based runs).
ensure_aws_cli_v2() {
  AWS_CLI_PATH="$(command -v aws || true)"
  if [ -n "${AWS_CLI_PATH:-}" ] && "$AWS_CLI_PATH" --version 2> /dev/null | grep -q "aws-cli/2"; then
    export AWS_CLI_PATH
    return 0
  fi

  echo "[SETUP] AWS CLI v2 not found. Installing..." >&2

  local sudo_cmd=""
  if [ "$(id -u)" -ne 0 ] && command -v sudo &> /dev/null; then
    sudo_cmd="sudo"
  fi

  pkgs=()
  if ! command -v curl &> /dev/null; then
    pkgs+=("curl")
  fi
  if ! command -v unzip &> /dev/null; then
    pkgs+=("unzip")
  fi
  if [ "${#pkgs[@]}" -gt 0 ]; then
    ${sudo_cmd} apt-get update -y
    ${sudo_cmd} apt-get install -y "${pkgs[@]}"
  fi

  local arch aws_arch tmpdir
  arch="$(uname -m)"
  case "$arch" in
    x86_64) aws_arch="x86_64" ;;
    aarch64 | arm64) aws_arch="aarch64" ;;
    *)
      echo "[SETUP] Unsupported architecture for AWS CLI: $arch" >&2
      exit 1
      ;;
  esac

  tmpdir="$(mktemp -d)"
  curl -sS "https://awscli.amazonaws.com/awscli-exe-linux-${aws_arch}.zip" -o "${tmpdir}/awscliv2.zip"
  unzip -q "${tmpdir}/awscliv2.zip" -d "${tmpdir}"
  ${sudo_cmd} "${tmpdir}/aws/install" --bin-dir /usr/local/bin --install-dir /usr/local/aws-cli --update
  rm -rf "${tmpdir}"

  AWS_CLI_PATH="/usr/local/bin/aws"
  export AWS_CLI_PATH
}

ensure_aws_cli_v2

# Setup SSH deploy key for GitHub access
setup_deploy_key() {
  echo "[SETUP] Fetching deploy key from AWS Secrets Manager..."
  mkdir -p ~/.ssh
  chmod 700 ~/.ssh

  $AWS_CLI_PATH secretsmanager get-secret-value \
    --secret-id "$DEPLOY_KEY_SECRET" \
    --query SecretString \
    --output text \
    --region us-east-1 > ~/.ssh/metta-deploy-key
  chmod 600 ~/.ssh/metta-deploy-key

  if ! grep -q "metta-deploy-key" ~/.ssh/config 2> /dev/null; then
    cat >> ~/.ssh/config << 'EOF'
Host github.com
  IdentityFile ~/.ssh/metta-deploy-key
  IdentitiesOnly yes
  StrictHostKeyChecking accept-new
EOF
  fi
  chmod 600 ~/.ssh/config
}

# Ensure /workspace exists and is writable
if [ ! -d /workspace ]; then
  mkdir -p /workspace 2> /dev/null || sudo mkdir -p /workspace
fi
if [ -w /workspace ]; then
  # Already writable, try to ensure ownership matches current user
  chown "$(id -u)":"$(id -g)" /workspace 2> /dev/null || true
elif ! sudo chown "$(id -u)":"$(id -g)" /workspace 2> /dev/null; then
  echo "[SETUP] Failed to chown /workspace; please ensure it is writable by $(id -un)" >&2
  exit 1
fi

# Setup deploy key before clone
setup_deploy_key

# Ensure repo exists (AMI doesn't include it by default)
if [ ! -d "${REPO_DIR}/.git" ]; then
  if [ -d "${REPO_DIR}" ]; then
    # Docker image has the code but .git was excluded via .dockerignore.
    # Initialize a repo in-place so fetch/checkout below can update to the
    # requested commit without discarding the pre-built venv.
    echo "[SETUP] Initializing git in existing directory (Docker image without .git)..."
    cd "${REPO_DIR}"
    git init
    git remote add origin "git@github.com:${GITHUB_REPOSITORY}.git"
  else
    echo "[SETUP] Cloning metta repo..."
    cd /workspace
    git clone "git@github.com:${GITHUB_REPOSITORY}.git" metta
  fi
fi

cd "${REPO_DIR}"

# Keep SSH for fetch (deploy key), HTTPS for push (with PAT)
git remote set-url origin git@github.com:${GITHUB_REPOSITORY}.git
git remote set-url --push origin https://github.com/${GITHUB_REPOSITORY}.git

# Configure git credential helper for HTTPS pushing
if [ -n "${GITHUB_PAT:-}" ]; then
  echo "[SETUP] Configuring git credentials for pushing..."
  git config --global credential.helper store
  echo "https://x-access-token:${GITHUB_PAT}@github.com" > ~/.git-credentials
  chmod 600 ~/.git-credentials

  # Ensure CLI tools (and our python wrappers) can find a GitHub token without relying on `gh auth`.
  # We already store the PAT on disk for git pushing; keep `GITHUB_TOKEN`/`GH_TOKEN` consistent.
  mkdir -p ~/.config/metta
  cat > ~/.config/metta/credentials.sh << EOF
export GITHUB_TOKEN="${GITHUB_PAT}"
export GH_TOKEN="${GITHUB_PAT}"
EOF
  chmod 600 ~/.config/metta/credentials.sh
fi

# Auto-cd to workspace on login
if ! grep -q "cd /workspace/metta" ~/.bashrc 2> /dev/null; then
  echo "cd /workspace/metta" >> ~/.bashrc
fi

# Load metta credentials (GitHub token) into interactive shells, including sweep-controller sandboxes.
if ! grep -q "source ~/.config/metta/credentials.sh" ~/.bashrc 2> /dev/null; then
  cat >> ~/.bashrc << 'EOF'
if [ -f ~/.config/metta/credentials.sh ]; then
  source ~/.config/metta/credentials.sh
fi
EOF
fi

git config advice.detachedHead false

echo "[SETUP] Fetching latest from origin..."
git fetch origin "$METTA_GIT_REF" || git fetch --depth=1000 origin
# -f: when .git was freshly init'd inside a Docker image, existing files are
# untracked and would otherwise block checkout.
git checkout -f "$METTA_GIT_REF"
echo "[SETUP] Checked out: $(git rev-parse HEAD)"

echo "[SETUP] Installing system dependencies..."
bash ./install.sh --profile softmax-docker --non-interactive

# Note that different sets of skypilot environment variables are available in "run" vs "setup"
# see https://docs.skypilot.co/en/latest/running-jobs/environment-variables.html
