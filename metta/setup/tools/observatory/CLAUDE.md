# Observatory Local Development

Guidance for Claude when assisting with Observatory development and debugging.

## Overview

Observatory is the tournament and job orchestration platform. It includes:

- **Backend API** (FastAPI) - Job management, tournament logic
- **Frontend** (Next.js) - Web UI
- **PostgreSQL** - Data storage
- **K8s Job Runner** - Executes policy evaluation jobs
- **Watcher** - Monitors K8s jobs, reports results
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

**Migrations:** Handled automatically in production when code merges. Local dev uses existing DB schema. Migration list
in `app_backend/src/metta/app_backend/migrations.py`.

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

## Architecture Notes

**K8s Runtime Detection:**

- Supports OrbStack (macOS) and k3d (devcontainer/Linux)
- Auto-detects via `detect_k8s_runtime()` in `local_k8s.py`
- Uses appropriate context and host address for each runtime

**Service Communication:**

- Services bind to `0.0.0.0` for devcontainer accessibility
- K8s pods reach backend via `host.docker.internal` (OrbStack) or `host.k3d.internal` (k3d)
- Frontend connects to backend via `OBSERVATORY_API_URL` env var
