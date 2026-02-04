#!/usr/bin/env bash

set -eu
REPO_DIR="/workspace/metta"
DEPLOY_KEY_SECRET="github/metta-deploy-key"

# Ensure the execution environment can
# pick up the image's aws installation
export PATH="/usr/local/bin:$PATH"

# Ensure AWS CLI v2 is present (installed in the training image).
ensure_aws_cli_v2() {
  if command -v aws &> /dev/null && aws --version 2> /dev/null | grep -q "aws-cli/2"; then
    return 0
  fi

  echo "Got AWS version:"
  if command -v aws > /dev/null; then
    aws --version
  else
    echo "  aws command not found at all"
  fi
  echo "[SETUP] AWS CLI v2 not found. Rebuild the training image to include AWS CLI v2." >&2
  exit 1
}

ensure_aws_cli_v2

# Setup SSH deploy key for GitHub access
setup_deploy_key() {
  echo "[SETUP] Fetching deploy key from AWS Secrets Manager..."
  mkdir -p ~/.ssh
  chmod 700 ~/.ssh

  aws secretsmanager get-secret-value \
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
if ! sudo chown "$(id -u)":"$(id -g)" /workspace 2> /dev/null; then
  echo "[SETUP] Failed to chown /workspace; please ensure it is writable by $(id -un)" >&2
  exit 1
fi

# Setup deploy key before clone
setup_deploy_key

# Ensure repo exists (AMI doesn't include it by default)
if [ ! -d "${REPO_DIR}/.git" ]; then
  if [ -d "${REPO_DIR}" ]; then
    echo "[SETUP] Found ${REPO_DIR} without a git repo; refusing to proceed. Please clean up the directory."
    exit 1
  fi

  echo "[SETUP] Cloning metta repo..."
  cd /workspace
  git clone git@github.com:${GITHUB_REPOSITORY}.git metta
fi

cd "${REPO_DIR}"

# Keep SSH for fetch (deploy key), HTTPS for push (with PAT)
git remote set-url origin git@github.com:${GITHUB_REPOSITORY}.git
git remote set-url --push origin https://github.com/${GITHUB_REPOSITORY}.git

# Configure git credential helper for HTTPS pushing
if [ -n "$GITHUB_PAT" ]; then
  echo "[SETUP] Configuring git credentials for pushing..."
  git config --global credential.helper store
  echo "https://x-access-token:${GITHUB_PAT}@github.com" > ~/.git-credentials
  chmod 600 ~/.git-credentials
fi

# Auto-cd to workspace on login
if ! grep -q "cd /workspace/metta" ~/.bashrc 2> /dev/null; then
  echo "cd /workspace/metta" >> ~/.bashrc
fi

git config advice.detachedHead false

echo "[SETUP] Fetching latest from origin..."
git fetch origin "$METTA_GIT_REF" || git fetch --depth=1000 origin
git checkout "$METTA_GIT_REF"
echo "[SETUP] Checked out: $(git rev-parse HEAD)"

echo "[SETUP] Installing system dependencies..."
bash ./install.sh --profile softmax-docker --non-interactive

# Note that different sets of skypilot environment variables are available in "run" vs "setup"
# see https://docs.skypilot.co/en/latest/running-jobs/environment-variables.html
