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

# Node.js 22 + Claude Code
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt-get install -y -qq nodejs
npm install -g @anthropic-ai/claude-code

# --- Pull secrets from Secrets Manager ---

REGION="us-east-1"
get_secret() { aws secretsmanager get-secret-value --secret-id "$1" --query SecretString --output text --region "$REGION"; }
get_secret_optional() { aws secretsmanager get-secret-value --secret-id "$1" --query SecretString --output text --region "$REGION" 2> /dev/null || echo ""; }

ANTHROPIC_API_KEY=$(get_secret "anthropic/agent-api-key")
OPENAI_API_KEY=$(get_secret_optional "openai/agent-api-key")
WANDB_API_KEY=$(get_secret "wandb/api-key")
DISCORD_WEBHOOK_URL=$(get_secret_optional "discord/agent-webhook-url")
GITHUB_APP_ID=$(get_secret "github/agent-app-id")
GITHUB_APP_PRIVATE_KEY=$(get_secret "github/agent-app-private-key")

mkdir -p /home/ubuntu/.config/metta
cat > /home/ubuntu/.config/metta/credentials.sh << CRED
export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}"
export OPENAI_API_KEY="${OPENAI_API_KEY}"
export WANDB_API_KEY="${WANDB_API_KEY}"
export DISCORD_WEBHOOK_URL="${DISCORD_WEBHOOK_URL}"
export AGENT_GITHUB_APP_ID="${GITHUB_APP_ID}"
export AGENT_GITHUB_APP_PRIVATE_KEY="${GITHUB_APP_PRIVATE_KEY}"
CRED
chmod 600 /home/ubuntu/.config/metta/credentials.sh

# --- WandB netrc ---

cat > /home/ubuntu/.netrc << NETRC
machine api.wandb.ai
login user
password ${WANDB_API_KEY}
NETRC
chmod 600 /home/ubuntu/.netrc
chown ubuntu:ubuntu /home/ubuntu/.netrc

# --- Generate GitHub App installation token ---

pip3 install --quiet PyJWT cryptography

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
payload = {"iat": now - 60, "exp": now + 600, "iss": int(app_id)}
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

# --- Configure git credentials with the token ---

git config --global credential.helper store
echo "https://x-access-token:${GITHUB_TOKEN}@github.com" > /root/.git-credentials
chmod 600 /root/.git-credentials

# --- Clone repos (full history, needed for branch operations) ---

git clone https://github.com/Metta-AI/metta.git /home/ubuntu/metta
git clone https://github.com/Metta-AI/cogents.git /home/ubuntu/cogents

# Move git credentials to ubuntu user (root was needed for clone)
mv /root/.git-credentials /home/ubuntu/.git-credentials
chown ubuntu:ubuntu /home/ubuntu/.git-credentials
su - ubuntu -c "git config --global credential.helper store"

# --- Git identity ---

su - ubuntu -c 'git config --global user.name "softmax-cogent[bot]"'
su - ubuntu -c 'git config --global user.email "softmax-cogent[bot]@users.noreply.github.com"'

# --- Bashrc: source credentials, cd to metta ---

cat >> /home/ubuntu/.bashrc << 'BASHRC'
if [ -f ~/.config/metta/credentials.sh ]; then
  source ~/.config/metta/credentials.sh
fi
cd /home/ubuntu/metta
BASHRC

# --- Agent log directory ---

mkdir -p /home/ubuntu/.agent/logs

# --- Fix ownership ---

chown -R ubuntu:ubuntu /home/ubuntu/.config
chown -R ubuntu:ubuntu /home/ubuntu/metta
chown -R ubuntu:ubuntu /home/ubuntu/cogents
chown -R ubuntu:ubuntu /home/ubuntu/.agent

touch /tmp/sandbox-ready
