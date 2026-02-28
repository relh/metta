#!/bin/bash
set -eu

export HOME=/root
export DEBIAN_FRONTEND=noninteractive

# --- Install system dependencies ---

apt-get update -qq
apt-get install -y -qq jq unzip python3-pip

# AWS CLI v2
if ! command -v aws &> /dev/null; then
  curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
  unzip -q /tmp/awscliv2.zip -d /tmp
  /tmp/aws/install
  rm -rf /tmp/aws /tmp/awscliv2.zip
fi

# Node.js 22 + Claude Code + Codex CLI
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt-get install -y -qq nodejs
npm install -g @anthropic-ai/claude-code @openai/codex

# SSM agent (for keyless SSH via AWS Session Manager)
if ! snap list amazon-ssm-agent &> /dev/null; then
  snap install amazon-ssm-agent --classic
fi
systemctl enable snap.amazon-ssm-agent.amazon-ssm-agent
systemctl start snap.amazon-ssm-agent.amazon-ssm-agent

# --- Pull boot-time secrets from Secrets Manager ---
# Runtime secrets are fetched on-demand by credentials.py — nothing persisted to disk.

REGION="us-east-1"
get_secret() { aws secretsmanager get-secret-value --secret-id "$1" --query SecretString --output text --region "$REGION"; }
get_secret_optional() { aws secretsmanager get-secret-value --secret-id "$1" --query SecretString --output text --region "$REGION" 2> /dev/null || echo ""; }

OPENAI_API_KEY=$(get_secret_optional "openai/agent-api-key")

# --- Generate GitHub App installation token ---

pip3 install --quiet --break-system-packages --ignore-installed PyJWT cryptography pydantic

GITHUB_TOKEN=$(
  python3 << 'PYEOF'
import json, time, urllib.request, jwt, sys

app_id = open("/proc/self/fd/3", "r").read().strip() if False else None
import subprocess
app_id = subprocess.check_output(
    ["aws", "secretsmanager", "get-secret-value", "--secret-id", "github/agent-app-id",
     "--query", "SecretString", "--output", "text", "--region", "us-east-1"],
    text=True).strip()
pem = subprocess.check_output(
    ["aws", "secretsmanager", "get-secret-value", "--secret-id", "github/agent-app-private-key",
     "--query", "SecretString", "--output", "text", "--region", "us-east-1"],
    text=True).strip()

now = int(time.time())
payload = {"iat": now - 60, "exp": now + 600, "iss": app_id}
encoded = jwt.encode(payload, pem, algorithm="RS256")

req = urllib.request.Request("https://api.github.com/app/installations",
    headers={"Authorization": f"Bearer {encoded}", "Accept": "application/vnd.github+json"})
installations = json.loads(urllib.request.urlopen(req).read())
install_id = installations[0]["id"]

req = urllib.request.Request(f"https://api.github.com/app/installations/{install_id}/access_tokens",
    method="POST",
    headers={"Authorization": f"Bearer {encoded}", "Accept": "application/vnd.github+json"})
token = json.loads(urllib.request.urlopen(req).read())["token"]
print(token)
PYEOF
)

# --- Git credential helper (serves token from GITHUB_TOKEN env var, nothing on disk) ---

mkdir -p /home/ubuntu/.agent
cat > /home/ubuntu/.agent/git-credential-helper << 'HELPER'
#!/bin/bash
if [ "$1" = "get" ]; then
  while IFS= read -r line && [ -n "$line" ]; do :; done
  echo "username=x-access-token"
  echo "password=$GITHUB_TOKEN"
fi
HELPER
chmod +x /home/ubuntu/.agent/git-credential-helper

git config --global credential.helper /home/ubuntu/.agent/git-credential-helper
export GITHUB_TOKEN

# --- Clone repos (full history, needed for branch operations) ---

git clone https://github.com/Metta-AI/metta.git /home/ubuntu/metta
git clone https://github.com/Metta-AI/cogents.git /home/ubuntu/cogents

# --- Git config for ubuntu user ---

su - ubuntu -c "git config --global credential.helper /home/ubuntu/.agent/git-credential-helper"

# --- Git identity ---

su - ubuntu -c 'git config --global user.name "softmax-cogent[bot]"'
su - ubuntu -c 'git config --global user.email "softmax-cogent[bot]@users.noreply.github.com"'

# --- Bashrc: load-secrets helper for interactive sessions, cd to metta ---

cat >> /home/ubuntu/.bashrc << 'BASHRC'
load-secrets() { eval "$(python3 /home/ubuntu/metta/devops/cogent/credentials.py --export)"; }
cd /home/ubuntu/metta
BASHRC

# --- Bedrock configuration (uses instance IAM role, no API key needed) ---

cat >> /home/ubuntu/.bashrc << 'BEDROCK'
export CLAUDE_CODE_USE_BEDROCK=1
export AWS_REGION=us-east-1
BEDROCK

# --- Crontab: poller runs every minute with Bedrock env vars ---

su - ubuntu -c 'crontab -' << 'CRON'
CLAUDE_CODE_USE_BEDROCK=1
AWS_REGION=us-east-1
* * * * * /usr/bin/python3 /home/ubuntu/cron_poller.py >> /home/ubuntu/.agent/logs/poller.log 2>&1
CRON

# --- Codex CLI auth ---

if [ -n "${OPENAI_API_KEY}" ]; then
  su - ubuntu -c 'codex login --with-api-key' <<< "${OPENAI_API_KEY}"
fi

# --- Agent log directory ---

mkdir -p /home/ubuntu/.agent/logs

# --- Fix ownership ---

mkdir -p /home/ubuntu/.config
chown -R ubuntu:ubuntu /home/ubuntu/.config
chown -R ubuntu:ubuntu /home/ubuntu/metta
chown -R ubuntu:ubuntu /home/ubuntu/cogents
chown -R ubuntu:ubuntu /home/ubuntu/.agent

touch /tmp/sandbox-ready
