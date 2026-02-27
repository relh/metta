# Observatory Local Development

Guidance for Claude when assisting with Observatory development and debugging.

## Overview

Observatory is the tournament and job orchestration platform. It includes:

- **Backend API** (FastAPI) - Job management, tournament logic
- **Frontend** (Next.js) - Web UI
- **PostgreSQL** - Data storage
- **K8s Job Runner** - Executes policy evaluation jobs
- **Watcher** - Monitors K8s pod events, stores them to database
- **Event Processor** - Processes stored events, reads results from S3, updates job statuses
- **Tournament Commissioner** - Creates matches, updates scores

## Quick Start

Run `metta observatory -h` for full command reference. Typical workflow:

```bash
# One-time: enable K8s and setup
metta observatory local-k8s setup

# Start services
metta observatory up
```

## Service URLs

- Frontend: http://127.0.0.1:5173
- API: http://127.0.0.1:8000

## Configuration

**Auth for local dev:**

```bash
metta install observatory-key-local  # Get machine token for local dev
```

**Python client for API calls:**

```python
from metta.app_backend.clients.stats_client import StatsClient
client = StatsClient.create("http://127.0.0.1:8000")
```

**Migrations:** Managed via Alembic. Observatory must be running (`metta observatory up`) so postgres is available. To
create a new migration after changing ORM models: `cd app_backend && alembic revision --autogenerate -m "description"`.
Review the generated file in `app_backend/alembic/versions/`, then commit. CI runs `test_autogenerate_is_empty` to catch
ORM/migration drift.

## Useful Commands

See `metta observatory -h` and `metta observatory local-k8s -h` for available commands.

## Debugging

When debugging Observatory issues:

1. **Check if services are running:**

   ```bash
   curl http://127.0.0.1:8000/whoami  # Backend health
   ```

2. **Check process-compose status:**

   ```bash
   curl http://127.0.0.1:8090/processes  # Service status
   ```

3. **Check K8s pods:**

   ```bash
   metta observatory local-k8s get-pods
   ```

4. **View logs:**

   ```bash
   metta observatory local-k8s logs [pod-name]  # K8s job logs
   ```

5. **Restart services if needed:**
   ```bash
   # Stop process-compose (Ctrl+C), then:
   metta observatory up
   ```

## Common Issues

### Server fails to start

- Check postgres is running: `docker ps | grep postgres`
- Check database URI is accessible
- View server logs in process-compose output

### Jobs not running

- Verify K8s is available: `metta observatory local-k8s status`
- Check namespace exists: `kubectl get namespace jobs`
- Verify image is available (OrbStack shares automatically, k3d needs import)

### Tournament scores not updating

- Check tournament service is running in process-compose
- Verify watcher is running and processing job results
- Check job completed successfully: `metta observatory local-k8s get-pods`

## Local Episode Runner Image

The local K8s setup builds a Docker image (`episode-runner-local:latest`) from source so local code changes are
reflected in job pods. This uses `Dockerfile.episode_runner.local` (in this directory), which is separate from the
production Dockerfile in `packages/cogames/`.

**Why a separate Dockerfile?** mettagrid has C++ extensions (pybind11/Bazel). Building on macOS produces a macOS wheel
that can't load in a Linux container. The local Dockerfile carries Bazel and a C++ toolchain so it can compile mettagrid
natively inside the container for the correct Linux platform.

**Platform:** On Apple Silicon, the image is built for `linux/arm64` (native, no QEMU emulation). On x86 hosts it builds
`linux/amd64`.

**Caching:** BuildKit cache mounts persist Bazel's build cache, uv's package cache, and Nim artifacts across rebuilds.
First build is slow (full C++ compile + dependency downloads); subsequent rebuilds after source changes are incremental.

**Rebuild after code changes:**

```bash
metta observatory local-k8s build-image   # Rebuild with local source
metta observatory local-k8s get-pods      # Check running pods
metta observatory local-k8s logs          # Follow pod logs
```

**Version pinning:** cogames pins `mettagrid==X.Y.Z` in its dependencies. The local Dockerfile uses
`uv pip install --override` to relax this constraint so the locally-built mettagrid (whatever version setuptools_scm
produces) is accepted alongside cogames.

## Running Single Episodes

`metta observatory run-episode` runs a single episode for debugging/testing. Three modes:

- **local** (default): subprocess isolation, no Docker. Fastest for iteration.
- **local-image**: uses `episode-runner-local:latest` built from source via `local-k8s build-image`.
- **prod-image**: pulls `ghcr.io/metta-ai/episode-runner:latest` (linux/amd64).

```bash
metta observatory run-episode job.json                  # Local subprocess
metta observatory run-episode job.json -m local-image   # Local Docker image
metta observatory run-episode job.json -m prod-image    # Production image
metta observatory run-episode <job-uuid> -m local-image # Fetch from observatory
```

Source can be a path to a job spec JSON file or an observatory job UUID.

## Architecture Notes

**K8s Runtime Detection:**

- Supports OrbStack (macOS) and k3d (devcontainer/Linux)
- Auto-detects via `detect_k8s_runtime()` in `local_k8s.py`
- Uses appropriate context and host address for each runtime

**Service Communication:**

- Services bind to `0.0.0.0` for devcontainer accessibility
- K8s pods reach backend via `host.docker.internal` (OrbStack) or `host.k3d.internal` (k3d)
- Frontend connects to backend via `OBSERVATORY_API_URL` env var
