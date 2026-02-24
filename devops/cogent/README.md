# Cogent — Agent Execution Platform

A dedicated EC2 instance that runs AI agent tasks on a schedule or on-demand via Claude Code CLI.

## How it works

The runner checks out a branch, reads a skill or prompt, and invokes `claude -p` with the content. Commits appear as
`softmax-cogent[bot]`. GitHub auth uses short-lived tokens from the Softmax Cogent GitHub App.

## Usage

SSH into the cogent instance and run:

```bash
# Run a shared skill on a branch
./agent-runner.py --branch main --skill cb.review-main

# Run a skill on a feature branch
./agent-runner.py --branch alex/my-feature --skill pr.check-ci

# Run a custom prompt (from devops/cogent/prompts/ on the target branch)
./agent-runner.py --branch alex/experiment --prompt check-training.md

# With a custom timeout (default: 60 min)
./agent-runner.py --branch main --skill cb.review-main --timeout 30
```

### `--skill`

Reads `SKILL.md` from the cogents repo (`Metta-AI/cogents`) at `skills/<name>/SKILL.md`. Skills are shared across all
branches. The cogents repo tracks the same branch if it exists, otherwise falls back to `main`.

### `--prompt`

Reads a prompt file from the metta repo at `devops/cogent/prompts/<path>`. Prompts are branch-specific — they come from
whatever branch `--branch` checks out. To add a custom prompt, create a file in `devops/cogent/prompts/` on your branch
and push.

### `--branch`

The git branch to check out on the metta repo before running. Defaults to `main`.

## Logs

Each run writes to `~/.agent/logs/<timestamp>-<skill-or-prompt>.log` with stdout, stderr, and exit code.

## Files

| File              | Description                                                                       |
| ----------------- | --------------------------------------------------------------------------------- |
| `agent-runner.py` | The runner script. Deployed to `/home/ubuntu/agent-runner.py` on the instance.    |
| `cogent-boot.sh`  | EC2 user-data script. Installs deps, pulls secrets, clones repos, configures git. |

## Infrastructure

- **Instance**: `t3.medium` in `us-east-1`, always-on (~$30/mo)
- **IAM role**: `cogent-role` with `cogent-profile`, grants `secretsmanager:GetSecretValue`
- **Secrets**: Stored in AWS Secrets Manager — Anthropic key, GitHub App credentials, WandB, Discord webhook, OpenAI
  (optional)
- **GitHub App**: "Softmax Cogent" — installed on `Metta-AI/metta` and `Metta-AI/cogents`
- **SSH key**: `cogent-ec2` key pair, private key at `~/.ssh/cogent-ec2.pem` on the provisioner's machine
