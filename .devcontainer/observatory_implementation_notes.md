# Observatory Devcontainer Implementation Notes

This document explains how `metta observatory` works inside a devcontainer, the challenges we solved, and how all the
pieces fit together.

## Overview

Observatory is a web application for monitoring ML training jobs. It consists of:

- **PostgreSQL** - Stores job metadata, tournament results, policies
- **FastAPI Backend** - API server at port 8000
- **Next.js Frontend** - Web UI at port 5173
- **Job Watcher** - Monitors K8s pods and updates job status
- **Tournament Commissioner** - Creates matches and updates scores
- **Kubernetes** - Runs policy evaluation job pods

The goal was to make `metta observatory up` work identically whether you're:

1. Running directly on macOS (the existing workflow)
2. Running inside a devcontainer on macOS

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                          HOST (macOS)                                │
│                                                                      │
│  ┌──────────────────┐     ┌──────────────────┐                      │
│  │    OrbStack      │     │  Docker Daemon   │                      │
│  │   (Kubernetes)   │     │                  │                      │
│  │                  │     │  ┌────────────┐  │                      │
│  │  ┌────────────┐  │     │  │  Postgres  │  │                      │
│  │  │ Job Pods   │  │     │  │   :5432    │  │                      │
│  │  └────────────┘  │     │  └────────────┘  │                      │
│  │                  │     │                  │                      │
│  │  API: 127.0.0.1  │     │                  │                      │
│  │  :26443          │     │                  │                      │
│  └────────────────┬─┘     └────────┬─────────┘                      │
│                   │                │                                 │
│                   │ ~/.kube/config │ /var/run/docker.sock           │
│                   │                │                                 │
│  ─────────────────┼────────────────┼─────────────────────────────── │
│                   │ (mounted)      │ (mounted)                       │
│  ┌────────────────┴────────────────┴─────────────────────────────┐  │
│  │                     DEVCONTAINER                               │  │
│  │                                                                │  │
│  │  ┌─────────────────────────────────────────────────────────┐  │  │
│  │  │                    metta observatory up                  │  │  │
│  │  │                                                          │  │  │
│  │  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │  │  │
│  │  │  │ Frontend │  │  Server  │  │ Watcher  │  │Tournament│ │  │  │
│  │  │  │  :5173   │  │  :8000   │  │          │  │          │ │  │  │
│  │  │  └──────────┘  └────┬─────┘  └────┬─────┘  └──────────┘ │  │  │
│  │  │                     │             │                      │  │  │
│  │  └─────────────────────┼─────────────┼──────────────────────┘  │  │
│  │                        │             │                         │  │
│  │         ┌──────────────┴─────────────┴──────────────┐         │  │
│  │         │         host.docker.internal               │         │  │
│  │         │  - Postgres at :5432                       │         │  │
│  │         │  - OrbStack K8s API at :26443              │         │  │
│  │         └────────────────────────────────────────────┘         │  │
│  │                                                                │  │
│  │  Modified kubeconfig: ~/.kube/config-container                 │  │
│  │  - server: https://orbstack:26443                              │  │
│  │  - Uses proper TLS verification (cert has "orbstack" SAN)      │  │
│  │                                                                │  │
│  └────────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  Exposed ports (via runArgs -p):                                     │
│  - localhost:5173 → container:5173 (Frontend)                        │
│  - localhost:8000 → container:8000 (Backend)                         │
│  - localhost:8090 → container:8090 (Process Compose UI)              │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Challenges and Solutions

### Challenge 1: Kubernetes Access from Container

**Problem:** OrbStack's kubeconfig uses `127.0.0.1:26443` for the K8s API server. From inside a container, `127.0.0.1`
refers to the container itself, not the host.

**Solution:** We use Docker's `--add-host` feature combined with OrbStack's certificate SANs:

1. The devcontainer runs with `--add-host=orbstack:host-gateway`, which makes the hostname "orbstack" resolve to the
   host's IP address from inside the container
2. We create a modified kubeconfig that replaces `https://127.0.0.1:` with `https://orbstack:`
3. OrbStack's K8s API server certificate includes "orbstack" as a SAN (Subject Alternative Name), so TLS verification
   works correctly

**Why this approach?** OrbStack's K8s API server certificate includes these SANs:

- localhost
- 127.0.0.1
- orbstack
- kubernetes

By using the "orbstack" hostname (which the cert is valid for) and making it resolve to the host IP, we get proper TLS
verification without needing `insecure-skip-tls-verify`.

**Implementation:** `local_k8s.py:_get_orbstack_kubeconfig_for_container()` and `devcontainer.json` runArgs

### Challenge 2: PostgreSQL Access from Container

**Problem:** When you run `metta observatory postgres up` in the devcontainer, it uses docker-compose to start postgres.
But the docker commands go to the HOST's Docker daemon (via the mounted socket), so postgres runs on the HOST, not
inside the devcontainer.

From the devcontainer's perspective, postgres isn't at `127.0.0.1:5432` - it's at `host.docker.internal:5432`.

**Solution:** The `_get_db_uri()` function in `cli.py` detects if we're in a container and returns the appropriate
connection string:

- Direct Mac: `postgres://...@127.0.0.1:5432/...`
- Devcontainer: `postgres://...@host.docker.internal:5432/...`

**Implementation:** `cli.py:_get_db_uri()` and `local_k8s.py:_is_running_in_container()`

### Challenge 3: Port Forwarding

**Problem:** VS Code's `forwardPorts` in devcontainer.json only works with VS Code's built-in port forwarding. When
using Cursor, CLI, or other tools, ports aren't forwarded.

**Solution:** Use explicit `-p` flags in `runArgs` which work at the Docker level:

```json
"runArgs": ["--platform=linux/amd64", "-p", "5173:5173", "-p", "8000:8000", "-p", "8090:8090"]
```

**Note:** We deliberately don't forward port 5432 because postgres runs on the host's Docker, not in the devcontainer.

### Challenge 4: Postgres Readiness Probe

**Problem:** The process-compose postgres readiness probe checks if postgres is accepting connections. In a container,
we need to probe `host.docker.internal:5432`, not `127.0.0.1:5432`.

**Solution:** `cli.py:_process_compose_env()` sets `POSTGRES_PROBE_HOST=host.docker.internal` when running in a
container. The probe in `process-compose.yaml` uses this:

```yaml
command:
  python -c "import socket; socket.create_connection(('${POSTGRES_PROBE_HOST:-${POSTGRES_HOST}}', ${POSTGRES_PORT}),
  timeout=1)"
```

### Challenge 5: Container Detection

**Problem:** We need to reliably detect if we're running in a container to apply the right configuration.

**Solution:** Multiple detection heuristics in `_is_running_in_container()`:

1. Check for `/.dockerenv` file (Docker creates this)
2. Check for `REMOTE_CONTAINERS` or `CODESPACES` env vars (VS Code sets these)
3. Check `/proc/1/cgroup` for "docker" or "kubepods" strings

## File-by-File Changes

### `.devcontainer/Dockerfile`

Added tools needed for observatory:

- **Docker CLI + Compose plugin** - For `docker compose` commands that control host Docker
- **kubectl** - For K8s management
- **k3d** - Alternative K8s runtime for Linux (not used on Mac devcontainers)
- **process-compose** - Service orchestration for observatory

### `.devcontainer/devcontainer.json`

Key additions:

- **runArgs with -p flags** - Port forwarding that works without VS Code
- **runArgs with --add-host** - Makes "orbstack" resolve to host IP for proper TLS
- **Docker socket mount** - Allows controlling host Docker
- **~/.kube mount** - Access to host's kubeconfig
- **~/.aws mount** - AWS credentials for job pods

### `metta/setup/tools/observatory/local_k8s.py`

Complete refactor for dual-runtime support:

- `_is_running_in_container()` - Container detection
- `_get_orbstack_kubeconfig_for_container()` - Modified kubeconfig generation
- `detect_k8s_runtime()` - Auto-detect OrbStack or k3d
- `_get_kubectl_env()` - Environment with correct KUBECONFIG

### `metta/setup/tools/observatory/cli.py`

Container-aware configuration:

- `_get_db_uri()` - Returns correct postgres URI for environment
- `_process_compose_env()` - Sets all env vars for container compatibility
- Module docstring explaining the architecture

### `metta/setup/tools/observatory/process-compose.yaml`

Generic healthchecks that work in both environments:

- K8s healthcheck uses `K8S_CONTEXT` env var
- Postgres probe uses `POSTGRES_PROBE_HOST` env var
- All kubectl commands use the context from environment

## Environment Variables

These are set by `cli.py:_process_compose_env()`:

| Variable              | Direct Mac               | Devcontainer                        | Purpose                  |
| --------------------- | ------------------------ | ----------------------------------- | ------------------------ |
| `K8S_CONTEXT`         | `orbstack`               | `orbstack`                          | kubectl context          |
| `KUBECONFIG`          | (default)                | `~/.kube/config-container`          | Modified kubeconfig path |
| `POSTGRES_HOST`       | `127.0.0.1`              | `127.0.0.1`                         | For postgres config      |
| `POSTGRES_PROBE_HOST` | (unset)                  | `host.docker.internal`              | For readiness probe      |
| `STATS_DB_URI`        | `...@127.0.0.1:5432/...` | `...@host.docker.internal:5432/...` | Server DB connection     |

## Runtime Selection Logic

```
detect_k8s_runtime():
  1. Check METTA_K8S_RUNTIME env var (explicit override)
  2. Create modified kubeconfig if in container
  3. List available kubectl contexts
  4. If "orbstack" context exists → use OrbStack
  5. If "k3d-metta-local" context exists → use k3d
  6. If k3d binary available → use k3d (can create cluster)
  7. If orbctl binary available → use OrbStack (need to enable K8s)
  8. None available → error
```

## Testing

See `.devcontainer/OBSERVATORY_TEST_PLAN.md` for the full test plan.

Quick verification:

```bash
# In devcontainer
metta observatory up

# In browser on host
open http://localhost:5173
```

Expected: Observatory web UI loads, shows policies page.

## Troubleshooting

### "Unable to connect to the server: x509: certificate is valid for localhost, orbstack, not host.docker.internal"

This error means the container is trying to connect via `host.docker.internal` instead of `orbstack`. Check:

1. `_is_running_in_container()` returns True
2. `~/.kube/config-container` uses `https://orbstack:` (not `host.docker.internal`)
3. The hostname "orbstack" resolves: `getent hosts orbstack` should return the host IP
4. If "orbstack" doesn't resolve, verify devcontainer.json has `--add-host=orbstack:host-gateway` in runArgs

### "Connection refused" to postgres

Postgres might not be running on host Docker. Check:

```bash
docker ps  # Should show postgres container
```

If not running, the devcontainer might not have the Docker socket mounted correctly.

### Ports not accessible from browser

Ensure runArgs has the -p flags:

```json
"runArgs": ["--platform=linux/amd64", "-p", "5173:5173", "-p", "8000:8000", "-p", "8090:8090"]
```

### InsecureRequestWarning in logs

If you see InsecureRequestWarning, it means TLS verification is being skipped somewhere. With the current implementation
using the "orbstack" hostname, you should NOT see these warnings. If you do, check that:

1. The kubeconfig uses `https://orbstack:` not `https://host.docker.internal:`
2. The kubeconfig has `certificate-authority-data` (not `insecure-skip-tls-verify`)
3. The "orbstack" hostname resolves correctly inside the container

## Design Decisions

### Why not run k3d inside the devcontainer?

For Mac users, OrbStack is already running and configured. Using it:

- Avoids running K8s-inside-Docker-inside-Docker
- Reuses existing setup and Docker images
- Simpler for developers

For Linux/remote users without OrbStack, we fall back to k3d.

### Why mount Docker socket instead of running Docker-in-Docker?

Docker-in-Docker has performance overhead and complexity. Mounting the socket is simpler and allows postgres to run on
the host where it's already configured.

### Why use process-compose instead of docker-compose for services?

process-compose runs services as local processes, which:

- Allows easier debugging (attach debugger, see logs directly)
- Shares the Python environment (no need to rebuild images)
- Faster iteration during development

Only postgres runs in Docker (via docker-compose) because it needs its own container.

## Debugging Techniques

This section documents the techniques we used to debug issues during development. These will help anyone who needs to
troubleshoot or extend this system in the future.

Each command is marked with where it should be run:

- **[CONTAINER]** - Run inside the devcontainer
- **[HOST]** - Run on the macOS host
- **[BOTH]** - Can be run in either environment (results may differ)

### Checking Container Detection

**[CONTAINER]** - Verify if the code correctly detects it's running in a container:

```bash
# [CONTAINER] Check detection function
python -c "from metta.setup.tools.observatory.local_k8s import _is_running_in_container; print(_is_running_in_container())"
# Should print: True

# [CONTAINER] Check what markers exist
ls -la /.dockerenv                    # Should exist in Docker containers
echo $REMOTE_CONTAINERS               # Set by VS Code devcontainers
cat /proc/1/cgroup | grep -E 'docker|kubepods'  # Shows container cgroup
```

**[HOST]** - Same check on host should return False:

```bash
# [HOST] Check detection function
python -c "from metta.setup.tools.observatory.local_k8s import _is_running_in_container; print(_is_running_in_container())"
# Should print: False
```

### Inspecting the Kubeconfig Modification

**[CONTAINER]** - The kubeconfig modification only happens inside the container:

```bash
# [CONTAINER] View the original (mounted from host)
cat ~/.kube/config | head -30

# [CONTAINER] Trigger the modification and view result
python -c "from metta.setup.tools.observatory.local_k8s import _get_orbstack_kubeconfig_for_container; print(_get_orbstack_kubeconfig_for_container())"

# [CONTAINER] View the modified version
cat ~/.kube/config-container | head -30

# [CONTAINER] Diff them to see exactly what changed
diff ~/.kube/config ~/.kube/config-container
```

Key things to verify:

- `server:` line changed from `127.0.0.1` to `orbstack`
- `certificate-authority-data:` is preserved (NOT replaced with `insecure-skip-tls-verify`)

### Testing Kubernetes Connectivity

**[CONTAINER]** - Test K8s access from inside the container:

```bash
# [CONTAINER] Test with the default kubeconfig (should FAIL)
kubectl --context orbstack cluster-info
# Expected error: "Unable to connect to the server: dial tcp 127.0.0.1:26443: connect: connection refused"

# [CONTAINER] Test with the modified kubeconfig (should WORK)
KUBECONFIG=~/.kube/config-container kubectl --context orbstack cluster-info
# Expected: "Kubernetes control plane is running at https://orbstack:26443"

# [CONTAINER] Check what contexts are available
kubectl config get-contexts
```

**[HOST]** - Test K8s access from the host:

```bash
# [HOST] Test with default kubeconfig (should WORK)
kubectl --context orbstack cluster-info
# Expected: "Kubernetes control plane is running at https://127.0.0.1:26443"
```

### Debugging TLS Certificate Issues

**[CONTAINER]** - Inspect the certificate from inside the container:

```bash
# [CONTAINER] View the certificate SANs (Subject Alternative Names)
echo | openssl s_client -connect orbstack:26443 2>/dev/null | openssl x509 -noout -text | grep -A1 "Subject Alternative Name"

# Expected output shows SANs that include "orbstack":
# DNS:localhost, DNS:orbstack, DNS:kubernetes, IP Address:127.0.0.1
```

**[HOST]** - Inspect from the host (use localhost instead):

```bash
# [HOST] View the certificate SANs
echo | openssl s_client -connect 127.0.0.1:26443 2>/dev/null | openssl x509 -noout -text | grep -A1 "Subject Alternative Name"
```

Since the cert includes "orbstack" as a SAN, using `https://orbstack:` allows proper TLS verification from the
container.

### Testing Docker Socket Access

**[CONTAINER]** - Verify the Docker socket is mounted and working:

```bash
# [CONTAINER] Verify socket is mounted
ls -la /var/run/docker.sock
# Should show: srw-rw---- ... /var/run/docker.sock

# [CONTAINER] Test docker commands work (controls HOST Docker)
docker ps
docker info | head -10

# [CONTAINER] Verify docker-compose works
docker compose version
```

**[HOST]** - Same commands work directly:

```bash
# [HOST] List containers (same output as from container)
docker ps
```

### Checking Network Connectivity

**[CONTAINER]** - Test network access to host services:

```bash
# [CONTAINER] Test host.docker.internal resolves
ping -c 1 host.docker.internal
# Should resolve to something like 192.168.65.254

# [CONTAINER] Test orbstack hostname resolves (for K8s)
getent hosts orbstack
# Should show the host gateway IP

# [CONTAINER] Test postgres connectivity (if running)
python -c "import socket; socket.create_connection(('host.docker.internal', 5432), timeout=2); print('OK')"

# [CONTAINER] Test K8s API connectivity via orbstack hostname
curl -k https://orbstack:26443/version
```

**[HOST]** - Test local services:

```bash
# [HOST] Test postgres connectivity
python -c "import socket; socket.create_connection(('127.0.0.1', 5432), timeout=2); print('OK')"

# [HOST] Test K8s API connectivity
curl -k https://127.0.0.1:26443/version
```

### Debugging Port Forwarding

**[CONTAINER]** - Check what's listening inside:

```bash
# [CONTAINER] Check what's listening
ss -tlnp | grep -E '5173|8000|8090'
```

**[HOST]** - Check port mappings and test connectivity:

```bash
# [HOST] Check port mappings on the devcontainer
docker ps --format "table {{.Names}}\t{{.Ports}}" | grep -i metta

# [HOST] Test connectivity to services running in container
curl -s http://localhost:8000/whoami | head -5   # Backend
curl -s http://localhost:5173 | head -5          # Frontend
```

### Debugging Runtime Detection

**[BOTH]** - These commands work in either environment but return different results:

```bash
# [BOTH] See what runtime is detected
python -c "from metta.setup.tools.observatory.local_k8s import detect_k8s_runtime; print(detect_k8s_runtime())"

# [BOTH] Check available contexts
kubectl config get-contexts -o name

# [BOTH] Force a specific runtime
METTA_K8S_RUNTIME=k3d python -c "from metta.setup.tools.observatory.local_k8s import detect_k8s_runtime; print(detect_k8s_runtime())"
```

### Debugging Process-Compose Environment

**[BOTH]** - Check environment variables (values differ by environment):

```bash
# [BOTH] See what environment process-compose receives
python -c "from metta.setup.tools.observatory.cli import _process_compose_env; import json; print(json.dumps(_process_compose_env(), indent=2))"

# Key variables to check:
# - K8S_CONTEXT: should be "orbstack" in both
# - KUBECONFIG: ~/.kube/config-container (container) vs default (host)
# - POSTGRES_PROBE_HOST: "host.docker.internal" (container) vs unset (host)
```

### Debugging Database Connectivity

**[BOTH]** - Check DB URI and test connection (URIs differ by environment):

```bash
# [BOTH] Check what DB URI is being used
python -c "from metta.setup.tools.observatory.cli import _get_db_uri; print(_get_db_uri())"
# In container: postgres://postgres:password@host.docker.internal:5432/metta
# On host:      postgres://postgres:password@127.0.0.1:5432/metta

# [BOTH] Test actual database connection (requires postgres running)
python -c "
import psycopg2
from metta.setup.tools.observatory.cli import _get_db_uri
uri = _get_db_uri()
print(f'Connecting to: {uri}')
conn = psycopg2.connect(uri)
print('Connected successfully!')
conn.close()
"
```

### Viewing Process-Compose Logs

**[BOTH]** - These work wherever observatory is running:

```bash
# [BOTH] Run with verbose output
metta observatory up 2>&1 | tee observatory.log

# [BOTH] In another terminal, check individual service status
curl -s http://localhost:8090/processes | python -m json.tool

# [BOTH] View logs for a specific process via the API
curl -s http://localhost:8090/process/server/logs
```

### Debugging OrbStack Directly

**[HOST]** - OrbStack commands only work on the macOS host:

```bash
# [HOST] Check OrbStack status
orb status

# [HOST] Check if K8s is enabled
orb config list | grep k8s

# [HOST] View OrbStack's K8s API server logs
orb logs k8s

# [HOST] Restart OrbStack K8s if needed
orbctl stop && orbctl start
```

### Common Debug Workflow

**[CONTAINER]** - When something isn't working inside the devcontainer, follow this sequence:

1. **Verify container detection**

   ```bash
   # [CONTAINER]
   python -c "from metta.setup.tools.observatory.local_k8s import _is_running_in_container; print(_is_running_in_container())"
   ```

2. **Verify orbstack hostname resolves**

   ```bash
   # [CONTAINER]
   getent hosts orbstack
   ```

3. **Verify kubeconfig modification**

   ```bash
   # [CONTAINER]
   cat ~/.kube/config-container | grep -E 'server:'
   # Should show: server: https://orbstack:26443
   ```

4. **Test K8s connectivity**

   ```bash
   # [CONTAINER]
   KUBECONFIG=~/.kube/config-container kubectl cluster-info
   ```

5. **Test postgres connectivity**

   ```bash
   # [CONTAINER]
   python -c "import socket; socket.create_connection(('host.docker.internal', 5432), timeout=2); print('OK')"
   ```

6. **Check environment variables**

   ```bash
   # [CONTAINER]
   python -c "from metta.setup.tools.observatory.cli import _process_compose_env; print(_process_compose_env())"
   ```

7. **Run with debug output**
   ```bash
   # [CONTAINER]
   metta observatory up 2>&1 | tee debug.log
   ```

### Using Claude Code for Debugging

During the development of this feature, we used Claude Code (the AI assistant) extensively for debugging. Some effective
techniques:

1. **Sharing error output directly** - Paste the full error message and stack trace
2. **Asking for diagnostic commands** - "What commands can I run to check if X is working?"
3. **Iterative debugging** - Share the output of diagnostic commands to narrow down the issue
4. **Checking assumptions** - "I assumed X, but is that correct given Y?"

For example, the TLS certificate issue was debugged by:

1. Sharing the x509 error message
2. Running `openssl s_client` to inspect the certificate (from container)
3. Confirming the SANs included "orbstack" but not "host.docker.internal"
4. Implementing the `--add-host=orbstack:host-gateway` solution
