import os
import subprocess
from datetime import datetime
from pathlib import Path

import boto3
from pydantic import BaseModel


class BoxInstance(BaseModel):
    instance_id: str
    name: str
    state: str
    ip: str
    git_ref: str
    repo: str
    instance_type: str
    launch_time: datetime


def _parse_instance(raw: dict) -> BoxInstance:
    tags = {t["Key"]: t["Value"] for t in raw.get("Tags", [])}
    return BoxInstance(
        instance_id=raw["InstanceId"],
        name=tags.get("Name", ""),
        state=raw["State"]["Name"],
        ip=raw.get("PublicIpAddress", ""),
        git_ref=tags.get("metta:git-ref", ""),
        repo=tags.get("metta:repo", ""),
        instance_type=raw["InstanceType"],
        launch_time=raw["LaunchTime"],
    )


# --- Bash script building blocks ---

_BASH_INSTALL_DEV_TOOLS = """\
# Install Node.js 22
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt-get install -y nodejs

# Install coding tools
npm install -g @anthropic-ai/claude-code @openai/codex @google/gemini-cli

# Install Go, Gas Town, and Beads
apt-get install -y libicu-dev
curl -fsSL https://go.dev/dl/go1.24.2.linux-amd64.tar.gz | tar -C /usr/local -xzf -
git clone https://github.com/steveyegge/gastown /home/ubuntu/gastown || echo "WARNING: gastown clone failed (non-fatal)"
mkdir -p /home/ubuntu/.local/bin
chown -R ubuntu:ubuntu /home/ubuntu/.local
su - ubuntu -c "cd /home/ubuntu/gastown && PATH=/usr/local/go/bin:\\$PATH \
  go build -buildvcs=false \
  -ldflags '-X github.com/steveyegge/gastown/internal/cmd.BuiltProperly=1' \
  -o /home/ubuntu/.local/bin/gt ./cmd/gt" || echo "WARNING: gastown build failed (non-fatal)"
su - ubuntu -c "PATH=/usr/local/go/bin:\\$PATH CGO_ENABLED=1 \
  go install github.com/steveyegge/beads/cmd/bd@latest" || echo "WARNING: beads install failed (non-fatal)"

# Pre-install nimby (urllib.request.urlretrieve chokes on GitHub 302 redirects)
curl -fsSL -o /home/ubuntu/.local/bin/nimby \
  https://github.com/treeform/nimby/releases/download/0.1.23/nimby-Linux-X64
chmod +x /home/ubuntu/.local/bin/nimby

# Initialize Gas Town
GT_PATH="/home/ubuntu/.local/bin:/usr/local/go/bin:/home/ubuntu/go/bin"
su - ubuntu -c "PATH=$GT_PATH:\\$PATH gt install ~/gt --git" || echo "WARNING: gt install failed (non-fatal)"
"""

_BASH_GIT_CREDENTIALS = """\
# Git credential store (x-access-token is internal, users see clean URLs)
su - ubuntu -c "git config --global credential.helper store"
echo "https://x-access-token:${GITHUB_PAT}@github.com" > /home/ubuntu/.git-credentials
chmod 600 /home/ubuntu/.git-credentials
chown ubuntu:ubuntu /home/ubuntu/.git-credentials

# gh CLI config (write directly, piping to su is unreliable)
mkdir -p /home/ubuntu/.config/gh
cat > /home/ubuntu/.config/gh/hosts.yml << GHCFG
github.com:
    oauth_token: ${GITHUB_PAT}
    user: ""
    git_protocol: https
GHCFG
chmod 600 /home/ubuntu/.config/gh/hosts.yml

# Token env vars for tools that read them
mkdir -p /home/ubuntu/.config/metta
cat > /home/ubuntu/.config/metta/credentials.sh << CRED
export GITHUB_TOKEN="$GITHUB_PAT"
export GH_TOKEN="$GITHUB_PAT"
CRED
chmod 600 /home/ubuntu/.config/metta/credentials.sh
chown -R ubuntu:ubuntu /home/ubuntu/.config
"""


def _bash_gastown_rig(repo_short: str, repo_dir: str) -> str:
    return f"""\
GT_PATH="/home/ubuntu/.local/bin:/usr/local/go/bin:/home/ubuntu/go/bin"
su - ubuntu -c "cd ~/gt && PATH=$GT_PATH:\\$PATH \
  gt rig add {repo_short} \
  https://github.com/${{GITHUB_REPOSITORY}}.git \
  --local-repo {repo_dir}"
"""


def _bash_bashrc(repo_dir: str) -> str:
    return f"""\
echo "cd {repo_dir}" >> /home/ubuntu/.bashrc
cat >> /home/ubuntu/.bashrc << 'BASHRC'
export PATH="$HOME/.local/bin:$PATH:/usr/local/go/bin:$HOME/go/bin"
if [ -f ~/.config/metta/credentials.sh ]; then
  source ~/.config/metta/credentials.sh
fi
BASHRC
"""


# --- EC2 operations ---


def get_ec2_client(profile: str = "sandbox", region: str = "us-east-1"):
    session = boto3.Session(profile_name=profile, region_name=region)
    return session.client("ec2")


def ensure_key_pair(ec2_client, username: str) -> tuple[str, Path]:
    key_name = f"{username}-sandbox"
    pub_key_path = Path.home() / ".ssh" / "id_ed25519.pub"
    private_key_path = Path.home() / ".ssh" / "id_ed25519"
    if not pub_key_path.exists():
        pub_key_path = Path.home() / ".ssh" / "id_rsa.pub"
        private_key_path = Path.home() / ".ssh" / "id_rsa"
    if not pub_key_path.exists():
        raise FileNotFoundError("No SSH public key found at ~/.ssh/id_ed25519.pub or ~/.ssh/id_rsa.pub")

    existing = ec2_client.describe_key_pairs(Filters=[{"Name": "key-name", "Values": [key_name]}])
    if not existing["KeyPairs"]:
        public_key_material = pub_key_path.read_bytes()
        ec2_client.import_key_pair(KeyName=key_name, PublicKeyMaterial=public_key_material)

    return key_name, private_key_path


def get_security_group(ec2_client) -> str:
    result = ec2_client.describe_security_groups(Filters=[{"Name": "group-name", "Values": ["metta-sandbox-ssh"]}])
    groups = result["SecurityGroups"]
    if not groups:
        raise RuntimeError("Security group 'metta-sandbox-ssh' not found. Run terraform apply in devops/tf/sandbox/.")
    return groups[0]["GroupId"]


def resolve_ubuntu_ami(ec2_client) -> str:
    result = ec2_client.describe_images(
        Owners=["099720109477"],
        Filters=[
            {"Name": "name", "Values": ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]},
            {"Name": "state", "Values": ["available"]},
        ],
    )
    images = sorted(result["Images"], key=lambda i: i["CreationDate"], reverse=True)
    if not images:
        raise RuntimeError("No Ubuntu 22.04 AMI found")
    return images[0]["ImageId"]


def build_bake_user_data(github_pat: str) -> str:
    repo = "Metta-AI/metta"
    repo_dir = "/home/ubuntu/metta"

    return f"""#!/bin/bash
set -eu

export HOME=/root

{_BASH_INSTALL_DEV_TOOLS}
# Clone metta repo and install
git clone "https://x-access-token:{github_pat}@github.com/{repo}.git" "{repo_dir}"
chown -R ubuntu:ubuntu "{repo_dir}"
su - ubuntu -c "cd {repo_dir} && bash ./install.sh --profile softmax-docker --non-interactive"
su - ubuntu -c "cd {repo_dir} && uv sync"

# Remove PAT from git remote (will be re-set at launch time)
su - ubuntu -c "cd {repo_dir} && git remote set-url origin https://github.com/{repo}.git"

{_bash_bashrc(repo_dir)}
touch /tmp/sandbox-ready
"""


def build_launch_user_data(github_pat: str, git_ref: str, repo: str) -> str:
    repo_short = repo.split("/")[-1]
    repo_dir = f"/home/ubuntu/{repo_short}"
    is_metta = repo in ("Metta-AI/metta", "metta-ai/metta")

    if is_metta:
        repo_setup = f"""
# Update pre-cloned metta repo to target ref
git config --global --add safe.directory "{repo_dir}"
cd "{repo_dir}"
git remote set-url origin "https://x-access-token:${{GITHUB_PAT}}@github.com/${{GITHUB_REPOSITORY}}.git"
git fetch origin "$GIT_REF"
git checkout "$GIT_REF" || git checkout FETCH_HEAD
git remote set-url origin "https://github.com/${{GITHUB_REPOSITORY}}.git"
chown -R ubuntu:ubuntu "{repo_dir}"
su - ubuntu -c "cd {repo_dir} && uv sync"
"""
    else:
        repo_setup = f"""
# Clone repo via HTTPS with PAT
git clone --depth=1000 -b "$GIT_REF" \
    "https://x-access-token:${{GITHUB_PAT}}@github.com/${{GITHUB_REPOSITORY}}.git" "{repo_dir}" || {{
    git clone "https://x-access-token:${{GITHUB_PAT}}@github.com/${{GITHUB_REPOSITORY}}.git" "{repo_dir}"
    cd "{repo_dir}"
    git fetch origin "$GIT_REF"
    git checkout "$GIT_REF"
}}
cd "{repo_dir}"
git remote set-url origin "https://github.com/${{GITHUB_REPOSITORY}}.git"
echo "cd {repo_dir}" >> /home/ubuntu/.bashrc
"""

    return f"""#!/bin/bash
set -eu

export HOME=/root
export GITHUB_PAT="{github_pat}"
export GITHUB_REPOSITORY="{repo}"
export GIT_REF="{git_ref}"
{repo_setup}
{_BASH_GIT_CREDENTIALS}
{_bash_gastown_rig(repo_short, repo_dir)}
chown -R ubuntu:ubuntu "{repo_dir}"
touch /tmp/sandbox-ready
"""


def build_user_data(github_pat: str, git_ref: str, repo: str) -> str:
    repo_short = repo.split("/")[-1]
    repo_dir = f"/home/ubuntu/{repo_short}"
    is_metta = repo in ("Metta-AI/metta", "metta-ai/metta")

    metta_setup = (
        f"""
su - ubuntu -c "cd {repo_dir} && bash ./install.sh --profile softmax-docker --non-interactive"
su - ubuntu -c "cd {repo_dir} && uv sync"
"""
        if is_metta
        else ""
    )

    return f"""#!/bin/bash
set -eu

export HOME=/root
export GITHUB_PAT="{github_pat}"
export GITHUB_REPOSITORY="{repo}"
export GIT_REF="{git_ref}"

REPO_DIR="{repo_dir}"

# Clone repo via HTTPS with PAT
git clone --depth=1000 -b "$GIT_REF" \
    "https://x-access-token:${{GITHUB_PAT}}@github.com/${{GITHUB_REPOSITORY}}.git" "$REPO_DIR" || {{
    git clone "https://x-access-token:${{GITHUB_PAT}}@github.com/${{GITHUB_REPOSITORY}}.git" "$REPO_DIR"
    cd "$REPO_DIR"
    git fetch origin "$GIT_REF"
    git checkout "$GIT_REF"
}}

cd "$REPO_DIR"
git remote set-url origin "https://github.com/${{GITHUB_REPOSITORY}}.git"

{_BASH_GIT_CREDENTIALS}
{_BASH_INSTALL_DEV_TOOLS}
{_bash_gastown_rig(repo_short, repo_dir)}
{_bash_bashrc(repo_dir)}
chown -R ubuntu:ubuntu "$REPO_DIR"
{metta_setup}
touch /tmp/sandbox-ready
"""


def launch_instance(
    ec2_client,
    name: str,
    instance_type: str,
    key_name: str,
    sg_id: str,
    user_data: str,
    username: str,
    git_ref: str,
    image_id: str,
    repo: str,
    volume_size: int = 200,
) -> str:
    result = ec2_client.run_instances(
        ImageId=image_id,
        InstanceType=instance_type,
        KeyName=key_name,
        SecurityGroupIds=[sg_id],
        UserData=user_data,
        MinCount=1,
        MaxCount=1,
        BlockDeviceMappings=[
            {
                "DeviceName": "/dev/sda1",
                "Ebs": {"VolumeSize": volume_size, "VolumeType": "gp3"},
            }
        ],
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Name", "Value": name},
                    {"Key": "metta:user", "Value": username},
                    {"Key": "metta:type", "Value": "aicode"},
                    {"Key": "metta:git-ref", "Value": git_ref},
                    {"Key": "metta:repo", "Value": repo},
                ],
            }
        ],
    )
    return result["Instances"][0]["InstanceId"]


def wait_for_running(ec2_client, instance_id: str) -> str:
    waiter = ec2_client.get_waiter("instance_running")
    waiter.wait(InstanceIds=[instance_id])
    result = ec2_client.describe_instances(InstanceIds=[instance_id])
    # KeyError intentional — sandbox instances must have public IPs
    return result["Reservations"][0]["Instances"][0]["PublicIpAddress"]


def list_user_instances(ec2_client, username: str) -> list[BoxInstance]:
    result = ec2_client.describe_instances(
        Filters=[
            {"Name": "tag:metta:user", "Values": [username]},
            {"Name": "tag:metta:type", "Values": ["aicode"]},
            {"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]},
        ]
    )
    return [_parse_instance(inst) for reservation in result["Reservations"] for inst in reservation["Instances"]]


def get_instance_by_name(ec2_client, name: str, username: str) -> BoxInstance | None:
    result = ec2_client.describe_instances(
        Filters=[
            {"Name": "tag:Name", "Values": [name]},
            {"Name": "tag:metta:user", "Values": [username]},
            {"Name": "tag:metta:type", "Values": ["aicode"]},
            {"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]},
        ]
    )
    for reservation in result["Reservations"]:
        for inst in reservation["Instances"]:
            return _parse_instance(inst)
    return None


def get_next_instance_name(ec2_client, username: str) -> str:
    instances = list_user_instances(ec2_client, username)
    existing_nums: set[int] = set()
    prefix = f"{username}-box-"
    for inst in instances:
        if inst.name.startswith(prefix):
            suffix = inst.name[len(prefix) :]
            if suffix.isdigit():
                existing_nums.add(int(suffix))
    n = 1
    while n in existing_nums:
        n += 1
    return f"{prefix}{n}"


def terminate_instance(ec2_client, instance_id: str) -> None:
    ec2_client.terminate_instances(InstanceIds=[instance_id])


def create_baked_ami(ec2_client, instance_id: str, name: str, username: str) -> str:
    result = ec2_client.create_image(
        InstanceId=instance_id,
        Name=name,
        NoReboot=False,
        TagSpecifications=[
            {
                "ResourceType": "image",
                "Tags": [
                    {"Key": "Name", "Value": name},
                    {"Key": "metta:type", "Value": "aicode-baked"},
                    {"Key": "metta:user", "Value": username},
                ],
            }
        ],
    )
    return result["ImageId"]


def wait_for_image(ec2_client, ami_id: str) -> None:
    waiter = ec2_client.get_waiter("image_available")
    waiter.wait(ImageIds=[ami_id], WaiterConfig={"Delay": 30, "MaxAttempts": 120})


def resolve_baked_ami(ec2_client) -> str | None:
    result = ec2_client.describe_images(
        Owners=["self"],
        Filters=[
            {"Name": "tag:metta:type", "Values": ["aicode-baked"]},
            {"Name": "state", "Values": ["available"]},
        ],
    )
    images = sorted(result["Images"], key=lambda i: i["CreationDate"], reverse=True)
    if not images:
        return None
    return images[0]["ImageId"]


def get_username() -> str:
    return os.environ.get("USER", "unknown")


def check_ssh_connection(ip: str, key_path: Path, timeout: int = 5) -> bool:
    result = subprocess.run(
        [
            "ssh",
            "-i",
            str(key_path),
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            "-o",
            f"ConnectTimeout={timeout}",
            "-o",
            "LogLevel=ERROR",
            f"ubuntu@{ip}",
            "test -f /tmp/sandbox-ready",
        ],
        capture_output=True,
    )
    return result.returncode == 0
