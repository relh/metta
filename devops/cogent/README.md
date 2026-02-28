# Cogent — Agent Execution Platform

A dedicated EC2 instance that runs AI agent tasks on a schedule or on-demand via Claude Code or Codex CLI.

## How it works

The runner creates isolated git worktrees for a branch, reads a skill and/or prompt, and invokes the chosen agent CLI
with the content. Multiple runs can execute concurrently on different branches. Commits appear as `softmax-cogent[bot]`.
GitHub auth uses short-lived tokens from the Softmax Cogent GitHub App.

## Connecting to the Instance

Connect via AWS SSM Session Manager (no SSH keys needed):

```bash
# One-time setup: install the Session Manager plugin
brew install --cask session-manager-plugin

# Connect (uses your existing AWS SSO profile)
aws ssm start-session --target i-08aef1bd88a87a5c0 --profile sandbox --region us-east-1

# Once connected, switch to the ubuntu user
sudo su - ubuntu
```

Any teammate with the `sandbox` AWS SSO profile can connect.

## Usage

On the instance, run:

```bash
# Run a shared skill on a branch
./agent-runner.py --branch main --skill cb.review-main

# Run a skill on a feature branch
./agent-runner.py --branch <feature-branch> --skill pr.check-ci

# Run a custom prompt (from devops/cogent/prompts/ on the target branch)
./agent-runner.py --branch <feature-branch> --prompt check-training.md

# Run a skill with additional context from a prompt
./agent-runner.py --branch <feature-branch> --skill pr.check-ci --prompt extra-context.md

# With a custom timeout (default: 60 min)
./agent-runner.py --branch main --skill cb.review-main --timeout 30

# Use Codex instead of Claude
./agent-runner.py --branch main --skill cb.review-main --agent codex
```

### `--branch` (required)

The git branch to create worktrees from on the metta repo (and cogents, with fallback to main).

### `--skill`

Reads `SKILL.md` from the cogents repo (`Metta-AI/cogents`) at `skills/<name>/SKILL.md`. Skills are shared across all
branches. The cogents repo tracks the same branch if it exists, otherwise falls back to `main`.

### `--prompt`

Reads a prompt file from the metta repo at `devops/cogent/prompts/<path>`. Prompts are branch-specific — they come from
whatever branch `--branch` checks out. To add a custom prompt, create a file in `devops/cogent/prompts/` on your branch
and push.

Both `--skill` and `--prompt` can be provided together — the skill content is sent first, followed by the prompt content
as additional context.

### `--agent`

Which agent CLI to use: `codex` (default) or `claude`. Claude uses `claude -p --verbose`, Codex uses
`codex exec --dangerously-bypass-approvals-and-sandbox`.

## Scheduling

A poller (`cron_poller.py`) runs every minute via cron. It reads jobs from three sources:

### 1. Checked-in schedule (`cron_schedule.py`)

Edit `cron_schedule.py` to add, remove, or change recurring jobs. Changes take effect after merge to main (the poller
reads from the metta checkout).

```python
JOBS = [
    Job(
        name="review-main",
        schedule=Schedule.weekdays(hour=9),
        branch="main",
        skill="cb.review-main",
    ),
]
```

### 2. Branch-submitted jobs (`.agent/jobs/*.md`)

Agents on feature branches can write a prompt file to `.agent/jobs/` and push to a branch under the `cogent/` prefix.
The poller scans these branches every minute and runs any jobs that are due.

Example — create `.agent/jobs/check-training.md` on branch `cogent/my-experiment`:

```markdown
---
schedule: weekdays 9:00
skill: cb.review-main
timeout: 30
---
```

Or use an inline prompt (the body is sent directly to the default agent):

```markdown
---
schedule: once
timeout: 45
---

Check the latest training metrics on WandB for the current branch and post a summary to Discord.
```

**Frontmatter fields:**

| Field      | Default | Description                                                                  |
| ---------- | ------- | ---------------------------------------------------------------------------- |
| `schedule` | `once`  | When to run: `once`, `every 5m`, `hourly :15`, `daily 9:00`, `weekdays 9:00` |
| `skill`    | —       | Skill name (reads from cogents repo)                                         |
| `prompt`   | —       | Prompt path (reads from `devops/cogent/prompts/` on the branch)              |
| `agent`    | `codex` | Agent CLI to use: `claude` or `codex`                                        |
| `timeout`  | `60`    | Timeout in minutes                                                           |

If no `skill` or `prompt` is specified, the markdown body is used as the prompt.

**One-shot cleanup:** Jobs with `schedule: once` (the default) are automatically deleted from the branch after they run.
The poller commits the removal as `[cogent] cleanup: completed one-shot job <filename>` and pushes.

**Branch prefix:** Only branches starting with `cogent/` are scanned. This is intentional — agents opt in by naming
their branch accordingly.

### 3. Asana tasks

Assign any Asana task to the **Cogent** user and the poller picks it up automatically. The agent receives the full task
context (name, description, comments, custom fields, tags, parent task, due date) as a structured prompt.

**How to use:**

1. Create a task in any Asana project. Write the description as the prompt.
2. Assign the task to the Cogent user (`cogents@softmax.com`).
3. The poller picks it up within one minute, posts a "Started working on branch `cogent/asana-{gid}`" comment, and
   dispatches the agent.
4. When the agent finishes, its response is posted as a comment on the task and the task is marked complete.

**Follow-ups:** To give the agent more work on the same task, mark the task incomplete and add a comment with the new
instruction. The poller detects the new comment and re-dispatches to the same branch. The agent sees the full comment
history (including its own prior responses) as context.

**Custom branch:** If the task has a custom field named `branch`, the agent works on that branch instead of creating
`cogent/asana-{gid}`. Use this for tasks like "review the CI on `alex/fix-training`".

**Skill override:** If the task has a custom field named `skill`, that skill is prepended to the prompt (same as
`--skill` + `--prompt-text` in the runner).

**Lifecycle:**

| State         | Trigger                              | What happens                                             |
| ------------- | ------------------------------------ | -------------------------------------------------------- |
| **Assigned**  | User assigns task to Cogent          | Poller picks it up on next tick                          |
| **Running**   | Poller dispatches                    | "Started" comment posted, `cogent:running` tag added     |
| **Done**      | Agent completes                      | Result comment posted, tag removed, task marked complete |
| **Follow-up** | User uncompletes task + adds comment | Poller detects new comment, re-dispatches same branch    |
| **Cancelled** | User reassigns away from Cogent      | Poller ignores — no longer assigned to Cogent            |
| **Failed**    | Agent errors or times out            | Error comment posted, tag removed, task left incomplete  |

## Concurrency

Multiple runs can execute concurrently on different branches. Each run creates isolated **git worktrees** under
`~/.agent/worktrees/<run-id>/` for both the metta and cogents repos. The shared clones at `/home/ubuntu/metta` and
`/home/ubuntu/cogents` are only used as fetch targets — they're never checked out by the runner.

Worktrees are cleaned up in three ways:

1. **Normal exit** — the runner removes its worktrees in a `finally` block.
2. **Startup pruning** — each new run checks for orphaned worktrees from crashed processes (via PID file) and removes
   them before proceeding.
3. **Poller sweep** — the poller runs `git worktree prune` and removes stale worktree directories every minute.

To run multiple tasks at once, just open multiple terminals and invoke `agent-runner.py` in each one.

**Fetching:** The runner does _not_ fetch — it creates worktrees from whatever refs were last fetched. The poller's
`repo-sync` job fetches both repos every 5 minutes. If you need fresher data for a manual run, run `repo-sync.py` first.

**Auto-deploy:** After fetching, `repo-sync.py` copies the cogent scripts (`agent-runner.py`, `cron_poller.py`,
`credentials.py`, `repo-sync.py`, `asana_client.py`) from the repo checkout to `/home/ubuntu/`. Only changed files are
overwritten. This means pushing to `main` automatically deploys within 5 minutes — no manual file copying needed.

## Logs

- Per-run logs: `~/.agent/logs/<timestamp>-<label>.log`
- Poller log: `~/.agent/logs/poller.log`
- Poller state: `~/.agent/poller_state.json`

## Files

| File               | Description                                                                        |
| ------------------ | ---------------------------------------------------------------------------------- |
| `agent-runner.py`  | The runner script. Deployed to `/home/ubuntu/agent-runner.py` on the instance.     |
| `cron_poller.py`   | Poller that ticks every minute, runs scheduled, branch, and Asana jobs.            |
| `cron_schedule.py` | Typed job definitions (Pydantic models). Replaces raw crontab for job management.  |
| `asana_client.py`  | Asana API wrapper + Pydantic models. Used by the poller for task pickup/posting.   |
| `repo-sync.py`     | Repo sync script. Refreshes GitHub App token and fetches both repos.               |
| `credentials.py`   | Shared module — fetches secrets from AWS Secrets Manager at runtime (no disk).     |
| `cogent-boot.sh`   | EC2 user-data script. Installs deps, clones repos, configures git.                 |
| `cogent.tf`        | Terraform source for IAM/SG (in `devops/tf/sandbox/`, applied to sandbox account). |

## Amazon Bedrock

Claude Code runs via **Amazon Bedrock** instead of the direct Anthropic API. The instance's IAM role authenticates with
Bedrock automatically — no `ANTHROPIC_API_KEY` needed.

### Environment variables

Set by `cogent-boot.sh` in both `.bashrc` (interactive) and the crontab (poller):

```bash
CLAUDE_CODE_USE_BEDROCK=1
AWS_REGION=us-east-1
```

### IAM permissions

The `cogent-role` IAM role needs these Bedrock permissions in addition to the existing Secrets Manager and SSM policies:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "BedrockClaudeCode",
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream", "bedrock:ListInferenceProfiles"],
      "Resource": [
        "arn:aws:bedrock:*:*:inference-profile/*",
        "arn:aws:bedrock:*:*:application-inference-profile/*",
        "arn:aws:bedrock:*:*:foundation-model/*"
      ]
    }
  ]
}
```

## Infrastructure

The cogent instance lives in the **sandbox account** (015142856185). IAM and networking resources are managed by
Terraform in `devops/tf/sandbox/cogent.tf`.

- **Account**: Sandbox (015142856185), `us-east-1`
- **Instance**: `t3.medium`, always-on (~$30/mo)
- **IAM role**: `cogent-role` with `cogent-profile` (Terraform-managed). Grants:
  - `secretsmanager:GetSecretValue` + `DescribeSecret` on sandbox account secrets
  - `AmazonSSMManagedInstanceCore` (SSM connectivity)
  - Bedrock invoke permissions for Claude Code (see above)
- **Security group**: `cogent-sg` — egress-only, no inbound (SSM doesn't need open ports)
- **Access**: AWS SSM Session Manager (any user with the `sandbox` SSO profile can connect)
- **Secrets**: Stored in AWS Secrets Manager (sandbox account), fetched at runtime by `credentials.py` (never persisted
  to disk). Includes: GitHub App credentials, WandB, Discord webhook, OpenAI (optional), Asana token + config
  (optional). For interactive sessions, run `load-secrets` to populate env vars.
- **GitHub App**: "Softmax Cogent" — installed on `Metta-AI/metta` and `Metta-AI/cogents`
- **SSH**: Disabled (no inbound ports on security group). Use SSM to connect.
