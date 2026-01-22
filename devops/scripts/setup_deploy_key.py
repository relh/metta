#!/usr/bin/env python3
"""Setup SSH deploy key for GitHub access via AWS Secrets Manager.

TODO: Remove this file when eval_task_worker is removed.
"""

import logging
import os
import stat
import sys

import boto3

logger = logging.getLogger(__name__)

DEPLOY_KEY_SECRET = "github/metta-deploy-key"
SSH_KEY_PATH = os.path.expanduser("~/.ssh/metta-deploy-key")
SSH_CONFIG_PATH = os.path.expanduser("~/.ssh/config")

SSH_CONFIG_BLOCK = """\
Host github.com
  IdentityFile ~/.ssh/metta-deploy-key
  IdentitiesOnly yes
  StrictHostKeyChecking accept-new
"""


def setup_ssh_deploy_key() -> None:
    logger.info("Setting up SSH deploy key for GitHub access")

    ssh_dir = os.path.dirname(SSH_KEY_PATH)
    os.makedirs(ssh_dir, mode=0o700, exist_ok=True)

    client = boto3.client("secretsmanager", region_name="us-east-1")
    response = client.get_secret_value(SecretId=DEPLOY_KEY_SECRET)
    private_key = response["SecretString"]

    with open(SSH_KEY_PATH, "w") as f:
        f.write(private_key)
    os.chmod(SSH_KEY_PATH, stat.S_IRUSR | stat.S_IWUSR)

    existing_config = ""
    if os.path.exists(SSH_CONFIG_PATH):
        with open(SSH_CONFIG_PATH) as f:
            existing_config = f.read()

    if "metta-deploy-key" not in existing_config:
        with open(SSH_CONFIG_PATH, "a") as f:
            f.write("\n" + SSH_CONFIG_BLOCK)
        os.chmod(SSH_CONFIG_PATH, stat.S_IRUSR | stat.S_IWUSR)

    logger.info("SSH deploy key configured")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="[SETUP] %(message)s", stream=sys.stderr)
    setup_ssh_deploy_key()


if __name__ == "__main__":
    main()
