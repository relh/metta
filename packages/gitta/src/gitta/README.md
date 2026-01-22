# Gitta

A lightweight Python library for Git operations and GitHub token management.

## Purpose

Gitta provides:

- **Git command wrapper**: Run git commands with consistent error handling
- **GitHub token management**: Get tokens from environment or `gh` CLI
- **Read-only GitHub API**: Query PRs, commits, workflow status

For creating PRs, use `gh` CLI or Graphite directly.

## Installation

```bash
# Part of the metta workspace
uv sync
```

## Usage

### Git Operations

```python
import gitta

# Run git commands
output = gitta.run_git("log", "--oneline", "-5")

# Get current state
branch = gitta.get_current_branch()
commit = gitta.get_current_commit()

# Check for changes
has_changes, status = gitta.has_unstaged_changes()
```

### GitHub Token

```python
import gitta

# Gets token from GITHUB_TOKEN env var or `gh auth token`
token = gitta.get_github_token()
```

### Read-Only GitHub API

```python
import gitta

# Check if commit is in a PR
pr_info = gitta.get_matched_pr("abc123", "owner/repo")

# Get commits
commits = gitta.get_commits(repo="owner/repo", branch="main")

# Get workflow runs
runs = gitta.get_workflow_runs(repo="owner/repo", workflow_filename="checks.yml")
```

## Error Handling

```python
try:
    gitta.run_git("push", "origin", "main")
except gitta.GitNotInstalledError:
    print("Git is not installed")
except gitta.NotAGitRepoError:
    print("Not in a git repository")
except gitta.GitError as e:
    print(f"Git command failed: {e}")
```

## Environment Variables

| Variable       | Description                              |
| -------------- | ---------------------------------------- |
| `GITHUB_TOKEN` | GitHub token (fallback: `gh auth token`) |
