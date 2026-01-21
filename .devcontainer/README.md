# Metta Development Container

This devcontainer provides a consistent Linux x86 development environment for the Metta project, regardless of your host
OS or architecture.

## Quick Start

1. **Install prerequisites:**
   - [Docker Desktop](https://www.docker.com/products/docker-desktop/)
   - An editor with devcontainer support:
     - [VS Code](https://code.visualstudio.com/) with the
       [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
     - [Cursor](https://cursor.com/) (VS Code fork, use Dev Containers extension)
     - [Windsurf](https://windsurf.com/) (built-in support)
     - [Zed](https://zed.dev/) (built-in support)
   - Or the [devcontainer CLI](https://github.com/devcontainers/cli): `npm install -g @devcontainers/cli`

2. **Start the container:**

   ```bash
   # Using CLI
   devcontainer up --workspace-folder .
   devcontainer exec --workspace-folder . bash

   # Or in VS Code: click "Reopen in Container"
   # Or in Zed: open the project and select "Open in Dev Container"
   ```

3. **Verify the environment:**

   ```bash
   # Check Python and dependencies are working
   python --version
   uv run python -c "import torch; print(f'torch {torch.__version__}')"

   # Check build tools
   bazel --version
   nim --version
   ```

4. **Run tests to confirm everything works:**

   ```bash
   metta pytest tests/ -v --co -q | head -20  # List available tests
   metta pytest tests/unit/ -v                 # Run unit tests
   ```

5. **Try the AI tools:**

   ```bash
   claude                    # Start Claude Code
   gh auth status            # Verify GitHub CLI is authenticated
   gt --help                 # Graphite CLI for PRs
   ```

6. **Make a test change:**

   ```bash
   # Edit a file (changes are visible on host too)
   echo "# test" >> /workspace/README.md
   git diff                  # See the change
   git checkout -- README.md # Revert it
   ```

7. **Validate the setup:**

   ```bash
   .devcontainer/devcheck.sh        # Run the validation script
   ```

   This checks all tools, credentials, and configuration.

8. **Done.** You're ready to develop. The workspace at `/workspace` is shared with your host machine, so changes appear
   in both places instantly.

## Tool Usage: Container vs Host

Since the workspace is shared between host and container, some tools work in both places while others are better suited
to one or the other.

| Tool                 | In Container                                                  | On Host                                        | Notes                                          |
| -------------------- | ------------------------------------------------------------- | ---------------------------------------------- | ---------------------------------------------- |
| **Claude Code**      | Primary use. Run `claude` for AI assistance with code changes | Can also run on host since workspace is shared | Credentials mounted from host                  |
| **OpenAI Codex**     | Primary use. Run `codex` for AI code generation               | Can also run on host                           | Credentials mounted from host                  |
| **Git / Graphite**   | Commit, push, create PRs with `git` or `gt`                   | Can also run on host                           | Both work since `.git` is in shared workspace  |
| **GitHub CLI**       | `gh pr`, `gh issue`, API operations                           | Can also run on host                           | Credentials mounted from host                  |
| **uv / Python**      | Primary use. `uv run`, `uv sync`, run tests                   | Avoid - different platform may cause issues    | Container ensures Linux x86 consistency        |
| **Bazel / Nim**      | Primary use. Build native components                          | Avoid - architecture differences               | Container has correct build toolchain          |
| **pytest / lint**    | Primary use. `metta pytest`, `metta lint`                     | Avoid - may behave differently                 | Run in container for CI parity                 |
| **gcloud**           | Service account ops, cloud commands                           | Primary use for auth (`gcloud auth login`)     | Auth requires browser, so authenticate on host |
| **Weights & Biases** | `wandb` CLI for experiment tracking                           | Auth on host (`wandb login`)                   | Auth requires browser                          |
| **SkyPilot**         | Cloud VM orchestration                                        | Auth on host (`sky check`)                     | Initial setup requires browser auth            |
| **Docker**           | Not available inside container                                | Build/push images, run other containers        | Container doesn't have Docker socket           |
| **IDE**              | N/A                                                           | VS Code, Cursor, Windsurf, Zed                 | IDE runs on host, connects to container        |

**General guidance:**

- **Code editing, AI tools, git**: Work in either location (shared workspace)
- **Building, testing, linting**: Use container (matches CI/production)
- **Browser-based auth**: Do on host first, credentials auto-mount into container
- **Docker operations**: Host only

## User Configuration

### Credentials

Your local credentials are automatically mounted into the container so you don't need to re-authenticate:

| Tool             | Host Location                  | Container Location                     |
| ---------------- | ------------------------------ | -------------------------------------- |
| Claude           | `~/.claude`                    | `/root/.claude`                        |
| OpenAI Codex     | `~/.codex`                     | `/root/.codex`                         |
| GitHub CLI       | `~/.config/gh`                 | `/root/.config/gh`                     |
| Google Cloud     | `~/.config/gcloud`             | `/root/.config/gcloud`                 |
| Weights & Biases | `~/.config/wandb` + `~/.netrc` | `/root/.config/wandb` + `/root/.netrc` |
| SkyPilot         | `~/.sky`                       | `/root/.sky`                           |
| Graphite         | `~/.config/graphite`           | `/root/.config/graphite`               |

**Why directories are created automatically:** Docker bind mounts fail if the source directory doesn't exist on the
host. Since not every developer uses every tool (e.g., some may not have `gcloud` installed), `hostsetup.sh` creates any
missing directories before the container starts. Empty directories mount successfully and don't affect tools you haven't
configured.

### Dotfiles

Place your personal shell configuration in `~/.config/devdotfiles/` on your host machine. If a setup script exists, it
will run automatically:

```
~/.config/devdotfiles/
├── setup.sh          # Runs automatically (also checks install.sh, bootstrap.sh)
├── .bashrc           # Your shell customizations
├── .gitconfig        # Git configuration
└── ...               # Any other dotfiles
```

Example `setup.sh`:

```bash
#!/bin/bash
SCRIPT_DIR="$(dirname "$0")"
cat "$SCRIPT_DIR/.bashrc" >> "$HOME/.bashrc"
cp "$SCRIPT_DIR/.gitconfig" "$HOME/.gitconfig"
```

## Implementation

### File Overview

```
.devcontainer/
├── devcontainer.json   # Main configuration
├── Dockerfile          # Container image definition
├── hostsetup.sh        # Runs on HOST before container creation
├── usersetup.sh        # Runs in CONTAINER after creation
├── devcheck.sh         # Validates container setup (run inside container)
└── README.md           # This file
```

### Execution Order

1. **`initializeCommand` → `hostsetup.sh`** (runs on host)
   - Creates missing credential directories so mounts don't fail

2. **Docker build** (uses cached layers when possible)
   - Ubuntu 24.04 base with build tools
   - uv package manager
   - Bazel, Nim, Nimby (via bootstrap.py)

3. **Container start with mounts**
   - Workspace mounted at `/workspace`
   - All credential directories mounted

4. **`postCreateCommand` → `usersetup.sh`** (runs in container)
   - `uv sync --frozen` to install Python dependencies
   - Runs dotfiles setup script if present
   - Logs to `/tmp/usersetup.log`

### devcontainer.json

Key configuration:

```jsonc
{
  "build": {
    "dockerfile": "Dockerfile",
    "options": ["--platform=linux/amd64"], // Force x86 even on ARM Macs
  },
  "runArgs": ["--platform=linux/amd64"],
  "initializeCommand": ".devcontainer/hostsetup.sh", // Host-side setup
  "mounts": [
    // Credential mounts - see table above
  ],
  "postCreateCommand": ".devcontainer/usersetup.sh", // Container-side setup
}
```

### Platform Emulation

The container runs as `linux/amd64` even on ARM Macs (via Docker's QEMU emulation). This ensures:

- Parity with CI/CD and production (Linux x86)
- Native dependencies build correctly
- No "works on my machine" issues from architecture differences

Performance is slightly slower than native, but consistency is worth it.

### Debugging

View setup logs (in the container):

```bash
cat /tmp/usersetup.log
```

Check mounted credentials (in the container):

```bash
ls -la ~/.claude ~/.config/gh ~/.config/graphite
```

Rebuild from scratch (from host):

```bash
devcontainer up --workspace-folder . --remove-existing-container
```

### Adding New Credential Mounts

1. Add the directory to `hostsetup.sh`:

   ```bash
   mkdir -p ~/.config/newtool
   ```

2. Add the mount to `devcontainer.json`:
   ```json
   "source=${localEnv:HOME}/.config/newtool,target=/root/.config/newtool,type=bind,consistency=cached"
   ```

## Troubleshooting

**Container fails to start with mount error:**

- Run `hostsetup.sh` manually: `.devcontainer/hostsetup.sh`
- Ensure Docker has file sharing access to your home directory

**Dependencies fail to install (timeout):**

- Large packages like `torch` may timeout. The script uses `UV_HTTP_TIMEOUT=300` but you can increase it in
  `usersetup.sh`

**Changes to devcontainer.json not taking effect:**

- Rebuild: `devcontainer up --workspace-folder . --remove-existing-container`

## Developer Notes: Modifying the Devcontainer

### What Triggers a Rebuild?

| Change                            | Rebuilds Image? | Recreates Container?        |
| --------------------------------- | --------------- | --------------------------- |
| `Dockerfile`                      | Yes             | Yes                         |
| `build.args` in devcontainer.json | Yes             | Yes                         |
| `mounts`                          | No (cached)     | Yes                         |
| `runArgs`                         | No (cached)     | Yes                         |
| `containerEnv`                    | No (cached)     | Yes                         |
| `customizations`                  | No (cached)     | Yes                         |
| `postCreateCommand`               | No (cached)     | Runs on new container       |
| `initializeCommand`               | No (cached)     | Runs on host each time      |
| `hostsetup.sh`                    | No              | Runs on host each time      |
| `usersetup.sh`                    | No              | Runs in container on create |

**Key insight:** Dockerfile `RUN` commands are cached as layers. `postCreateCommand` runs every time a new container is
created. Prefer installing tools in the Dockerfile for faster container startup.

### Testing Changes Efficiently

**Quick iteration on usersetup.sh:**

```bash
# Run directly inside an existing container (no rebuild)
devcontainer exec --workspace-folder . bash
.devcontainer/usersetup.sh
cat /tmp/usersetup.log
```

**Test Dockerfile changes:**

```bash
# Rebuild image and recreate container
devcontainer up --workspace-folder . --remove-existing-container
```

**Test just the container (reuse image):**

```bash
# Faster - only recreates container, reuses cached image
devcontainer up --workspace-folder . --remove-existing-container --cache-from ""
```

**Test hostsetup.sh:**

```bash
# Run directly on host
.devcontainer/hostsetup.sh
```

### Debugging Build Failures

**View full build output:**

```bash
devcontainer up --workspace-folder . --log-level debug
```

**Build the Dockerfile directly (bypass devcontainer):**

```bash
docker build --platform=linux/amd64 -f .devcontainer/Dockerfile -t metta-dev-test .
docker run --rm -it --platform=linux/amd64 metta-dev-test bash
```

**Check layer cache usage:**

```bash
docker build --platform=linux/amd64 -f .devcontainer/Dockerfile -t metta-dev-test . 2>&1 | grep -E "(CACHED|RUN)"
```

### Best Practices

1. **Order Dockerfile commands by change frequency** - Put rarely-changing commands (system packages) early,
   frequently-changing commands (your tools) later. This maximizes cache hits.

2. **Combine related RUN commands** - Each `RUN` creates a layer. Combine related installs to reduce layers, but not so
   much that a small change invalidates a large layer.

3. **Test on a clean container** - Before committing, test with `--remove-existing-container` to ensure the full setup
   works.

4. **Check the logs** - `usersetup.sh` logs to `/tmp/usersetup.log`. Always check this when debugging setup issues.

5. **Use `.dockerignore`** - Large files in the build context slow down builds. The project's `.dockerignore` excludes
   `node_modules`, `.venv`, etc.

## Future Considerations

### Version Pinning Strategy

Currently, some tools in the Dockerfile use pinned versions while others fetch latest:

| Tool        | Current Approach          | Pinned?                 |
| ----------- | ------------------------- | ----------------------- |
| Ubuntu      | `24.04`                   | Yes                     |
| uv          | `0.9.5`                   | Yes                     |
| Python      | `.python-version` file    | Yes                     |
| Go          | `1.23.5`                  | Yes                     |
| Nushell     | `0.101.0`                 | Yes                     |
| Node.js     | `22.x`                    | Major only              |
| Rust        | `rustup` latest           | No                      |
| Claude Code | `npm` latest              | No                      |
| Codex       | `npm` latest              | No                      |
| Starship    | Install script latest     | No                      |
| Bazel/Nim   | `bootstrap.py` controlled | Yes (via version files) |

**Tradeoffs:**

- **Pinned versions**: Reproducible builds, but requires manual updates and can miss security patches
- **Latest versions**: Always current, but builds may break unexpectedly or behave differently over time

**Recommended approach:**

1. Pin versions for core build tools (Python, Bazel, Nim) - these affect build reproducibility
2. Pin major versions for languages (Node 22.x, Go 1.23.x) - breaking changes are rare within major versions
3. Allow latest for developer tools (Claude, Codex, Starship) - these don't affect builds and users benefit from updates
4. Consider a scheduled job to rebuild and test the container with updated versions

### Other Future Items

- **Pre-built container images**: Push to a registry (ghcr.io) to skip build time on first use
- **CI integration**: Run CI checks inside the devcontainer to ensure parity
- **GPU support**: Add NVIDIA container runtime configuration for ML workloads
- **Multi-architecture**: Build both `amd64` and `arm64` images for native performance on ARM Macs
- **Devcontainer features**: The [devcontainer features](https://containers.dev/features) ecosystem provides
  pre-packaged tool installers. Tradeoffs vs Dockerfile `RUN` commands:

  | Aspect        | Dockerfile RUN                      | Devcontainer Features                  |
  | ------------- | ----------------------------------- | -------------------------------------- |
  | Transparency  | Full control, visible in Dockerfile | Abstracted, must read feature source   |
  | Caching       | Docker layer caching                | Runs after image build, no layer cache |
  | Portability   | Works with any Docker tooling       | Requires devcontainer-aware tooling    |
  | Maintenance   | You maintain install scripts        | Community maintains features           |
  | Composability | Manual, can conflict                | Designed to compose cleanly            |

  Current approach: Dockerfile commands for transparency and caching. Consider features for complex tools where
  community maintenance is valuable (e.g., Docker-in-Docker, SSH server).
