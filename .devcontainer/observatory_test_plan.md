# Observatory Devcontainer Test Plan

This test plan verifies that `metta observatory` works correctly inside a devcontainer. Tests are ordered from simplest
(infrastructure) to most complex (full integration), allowing you to catch problems early.

## How to Use This Test Plan

### For Claude Code

When asked to test observatory devcontainer support, follow this plan sequentially. For tests marked **[HUMAN]**, prompt
the user to perform the action and report the result. For tests marked **[CLAUDE]**, execute the commands directly.

### For Humans

Work through the tests in order. Each test builds on the previous ones, so if an early test fails, fix it before
proceeding.

---

## Prerequisites

Before starting, ensure:

1. You have a Mac with OrbStack installed
2. OrbStack K8s is enabled
3. The devcontainer is built and running

### Pre-test Setup (Human)

**[HUMAN]** On the Mac host (not in devcontainer), verify OrbStack:

```bash
orbctl status
kubectl --context orbstack cluster-info
```

Expected: OrbStack running, K8s at `https://127.0.0.1:26443`

**[HUMAN]** Open the devcontainer (VS Code → "Reopen in Container" or similar)

---

## Phase 1: Infrastructure Tests

These tests verify the basic infrastructure is in place. If these fail, nothing else will work.

### Test 1.1: Container Detection

**[CLAUDE]** Verify the code detects it's running in a container.

```bash
python -c "from metta.setup.tools.observatory.local_k8s import _is_running_in_container; print('IN_CONTAINER:', _is_running_in_container())"
```

**Expected:** `IN_CONTAINER: True`

**If it fails:** Check for `/.dockerenv` file or `REMOTE_CONTAINERS` env var.

---

### Test 1.2: Docker Socket Access

**[CLAUDE]** Verify Docker commands work (using host's Docker daemon).

```bash
ls -la /var/run/docker.sock && docker ps --format "table {{.Names}}\t{{.Status}}" | head -5
```

**Expected:** Socket exists, `docker ps` shows running containers.

**If it fails:** Check devcontainer.json has the socket mount:

```json
"source=/var/run/docker.sock,target=/var/run/docker.sock,type=bind"
```

---

### Test 1.3: Kubeconfig Mount

**[CLAUDE]** Verify host's kubeconfig is mounted.

```bash
cat ~/.kube/config | grep -E "server:|name:" | head -6
```

**Expected:** Shows `server: https://127.0.0.1:26443` and context names including `orbstack`.

**If it fails:** Check devcontainer.json has the kube mount:

```json
"source=${localEnv:HOME}/.kube,target=/root/.kube,type=bind,consistency=cached"
```

---

### Test 1.4: Required Tools Installed

**[CLAUDE]** Verify all required CLI tools are available.

```bash
echo "kubectl: $(kubectl version --client -o json 2>/dev/null | python -c 'import sys,json; print(json.load(sys.stdin)["clientVersion"]["gitVersion"])' 2>/dev/null || echo 'MISSING')"
echo "docker: $(docker --version 2>/dev/null | cut -d' ' -f3 | tr -d ',' || echo 'MISSING')"
echo "docker-compose: $(docker compose version --short 2>/dev/null || echo 'MISSING')"
echo "k3d: $(k3d version 2>/dev/null | head -1 | awk '{print $3}' || echo 'MISSING')"
echo "process-compose: $(process-compose version 2>/dev/null | awk '{print $3}' || echo 'MISSING')"
```

**Expected:** All tools show version numbers, none say MISSING.

**If it fails:** Rebuild the devcontainer. Check Dockerfile has the tool installations.

---

## Phase 2: Network Connectivity Tests

These tests verify the container can reach host services.

### Test 2.1: host.docker.internal Resolution

**[CLAUDE]** Verify the Docker DNS name resolves.

```bash
python -c "import socket; ip = socket.gethostbyname('host.docker.internal'); print(f'host.docker.internal -> {ip}')"
```

**Expected:** Shows an IP address (e.g., `192.168.65.254`).

**If it fails:** This is a Docker/OrbStack networking issue. Restart Docker/OrbStack.

---

### Test 2.2: K8s API Reachability (Raw)

**[CLAUDE]** Test raw TCP connectivity to OrbStack's K8s API.

```bash
python -c "
import socket
try:
    socket.create_connection(('host.docker.internal', 26443), timeout=5)
    print('K8s API port reachable: OK')
except Exception as e:
    print(f'K8s API port reachable: FAILED - {e}')
"
```

**Expected:** `K8s API port reachable: OK`

**If it fails:**

- **[HUMAN]** Verify OrbStack K8s is running: `kubectl --context orbstack cluster-info`
- Check OrbStack's K8s port (usually 26443)

---

## Phase 3: Kubeconfig Modification Tests

These tests verify our kubeconfig modification logic works correctly.

### Test 3.1: Modified Kubeconfig Generation

**[CLAUDE]** Verify the modified kubeconfig is created correctly.

```bash
python -c "from metta.setup.tools.observatory.local_k8s import _get_orbstack_kubeconfig_for_container; path = _get_orbstack_kubeconfig_for_container(); print(f'Modified config path: {path}')"
```

**Expected:** Shows path like `/root/.kube/config-container`

**If it fails:** Check that `~/.kube/config` contains "orbstack" and "127.0.0.1".

---

### Test 3.2: Kubeconfig Content Verification

**[CLAUDE]** Verify the modifications are correct.

```bash
echo "=== Original (should have 127.0.0.1) ===" && grep "server:" ~/.kube/config | head -1
echo ""
echo "=== Modified (should have host.docker.internal) ===" && grep "server:" ~/.kube/config-container | head -1
echo ""
echo "=== TLS setting (should have insecure-skip-tls-verify) ===" && grep -E "insecure-skip-tls-verify|certificate-authority-data" ~/.kube/config-container | head -1
```

**Expected:**

- Original: `server: https://127.0.0.1:26443`
- Modified: `server: https://host.docker.internal:26443`
- TLS: `insecure-skip-tls-verify: true`

**If it fails:** Check the regex in `_get_orbstack_kubeconfig_for_container()`.

---

### Test 3.3: kubectl with Modified Config

**[CLAUDE]** Verify kubectl works with the modified config.

```bash
KUBECONFIG=~/.kube/config-container kubectl --context orbstack cluster-info 2>&1 | head -3
```

**Expected:** Shows "Kubernetes control plane is running at https://host.docker.internal:26443"

**If it fails:**

- If TLS error mentioning "host.docker.internal": the `insecure-skip-tls-verify` isn't set
- If connection refused: host.docker.internal isn't reaching the K8s API

---

## Phase 4: Runtime Detection Tests

These tests verify automatic runtime detection works.

### Test 4.1: Runtime Detection

**[CLAUDE]** Verify OrbStack is detected as the runtime.

```bash
python -c "from metta.setup.tools.observatory.local_k8s import detect_k8s_runtime; r = detect_k8s_runtime(); print(f'Detected runtime: {r.value if r else None}')"
```

**Expected:** `Detected runtime: orbstack`

**If it fails:** Check that the modified kubeconfig is used during detection (see `detect_k8s_runtime()`).

---

### Test 4.2: Runtime Status Command

**[CLAUDE]** Verify the status command works.

```bash
metta observatory local-k8s status
```

**Expected:**

```
✓ Runtime: orbstack
ℹ Context: orbstack
ℹ Host address (for pods): host.docker.internal
✓ Cluster is reachable
```

**If it fails:** Run the previous tests to identify which component is broken.

---

## Phase 5: Database Tests

These tests verify PostgreSQL connectivity from the container.

### Test 5.1: Database URI Detection

**[CLAUDE]** Verify the correct DB URI is generated for container environment.

```bash
python -c "from metta.setup.tools.observatory.cli import _get_db_uri; print(f'DB URI: {_get_db_uri()}')"
```

**Expected:** `DB URI: postgres://postgres:password@host.docker.internal:5432/metta`

Note: Should use `host.docker.internal`, NOT `127.0.0.1`.

**If it fails:** Check `_is_running_in_container()` returns True.

---

### Test 5.2: Start PostgreSQL

**[CLAUDE]** Start postgres via docker-compose (runs on host's Docker).

```bash
metta observatory postgres up -d --wait 2>&1 | tail -5
```

**Expected:** Shows postgres container starting/running.

---

### Test 5.3: PostgreSQL Connectivity

**[CLAUDE]** Verify we can connect to postgres from the container.

```bash
python -c "
import socket
try:
    socket.create_connection(('host.docker.internal', 5432), timeout=5)
    print('Postgres reachable: OK')
except Exception as e:
    print(f'Postgres reachable: FAILED - {e}')
"
```

**Expected:** `Postgres reachable: OK`

**If it fails:**

- Check postgres is running: `docker ps | grep postgres`
- Check it's on the host's Docker, not in the container

---

### Test 5.4: Database Connection Test

**[CLAUDE]** Test actual database connection with credentials.

```bash
python -c "
from metta.setup.tools.observatory.cli import _get_db_uri
import psycopg2
uri = _get_db_uri()
print(f'Connecting to: {uri}')
try:
    conn = psycopg2.connect(uri)
    print('Database connection: OK')
    conn.close()
except Exception as e:
    print(f'Database connection: FAILED - {e}')
"
```

**Expected:** `Database connection: OK`

---

## Phase 6: Process-Compose Environment Tests

These tests verify the environment is set up correctly for all services.

### Test 6.1: Environment Variables

**[CLAUDE]** Verify process-compose environment is configured correctly.

```bash
python -c "
from metta.setup.tools.observatory.cli import _process_compose_env
env = _process_compose_env()
print(f'K8S_CONTEXT: {env.get(\"K8S_CONTEXT\")}')
print(f'KUBECONFIG: {env.get(\"KUBECONFIG\", \"(default)\")}')
print(f'POSTGRES_PROBE_HOST: {env.get(\"POSTGRES_PROBE_HOST\", \"(not set)\")}')
"
```

**Expected:**

- `K8S_CONTEXT: orbstack`
- `KUBECONFIG: /root/.kube/config-container` (or similar)
- `POSTGRES_PROBE_HOST: host.docker.internal`

---

## Phase 7: Service Startup Tests

These tests verify individual services start correctly.

### Test 7.1: Backend Server Startup

**[CLAUDE]** Start just the backend server (depends on postgres).

```bash
timeout 30 metta observatory server 2>&1 &
SERVER_PID=$!
sleep 10
curl -s http://127.0.0.1:8000/whoami | head -3 || echo "Server not responding"
kill $SERVER_PID 2>/dev/null
```

**Expected:** Shows JSON response from `/whoami` endpoint.

**If it fails:** Check postgres is running and DB URI is correct.

---

### Test 7.2: Port Accessibility from Host

**[HUMAN]** With the server running in devcontainer, test from the Mac host:

```bash
curl -s http://localhost:8000/whoami | head -3
```

**Expected:** Same JSON response as from inside the container.

**If it fails:** Check devcontainer.json has `-p 8000:8000` in runArgs.

---

## Phase 8: Full Integration Tests

These tests verify everything works together.

### Test 8.1: Observatory Up (All Services)

**[CLAUDE]** Start all observatory services.

```bash
echo "Starting observatory services..."
timeout 60 bash -c 'metta observatory up 2>&1' &
UP_PID=$!
sleep 30

echo ""
echo "=== Checking services ==="
echo "Backend API:"
curl -s http://127.0.0.1:8000/whoami | head -1 || echo "  NOT RESPONDING"
echo ""
echo "Frontend:"
curl -s http://127.0.0.1:5173 | head -1 || echo "  NOT RESPONDING"
echo ""
echo "Process Compose:"
curl -s http://127.0.0.1:8090/processes | python -c "import sys,json; procs=json.load(sys.stdin); print('  Services:', [p['name'] for p in procs])" 2>/dev/null || echo "  NOT RESPONDING"

kill $UP_PID 2>/dev/null
```

**Expected:** All three endpoints respond.

---

### Test 8.2: Web UI Access

**[HUMAN]** Open a browser on the Mac host and navigate to:

- http://localhost:5173

**Expected:** Observatory web UI loads, shows the policies page.

---

### Test 8.3: K8s Namespace Setup

**[CLAUDE]** Set up the jobs namespace for running pods.

```bash
metta observatory local-k8s setup 2>&1 | tail -10
```

**Expected:**

- Shows "Using K8s runtime: orbstack"
- Creates/confirms jobs namespace
- Builds policy evaluator image

---

### Test 8.4: Verify K8s Access from Services

**[CLAUDE]** With observatory running, verify K8s commands work.

```bash
# This uses the same env that watcher uses
kubectl --context orbstack get namespaces | grep jobs || echo "jobs namespace not found"
```

**Expected:** Shows `jobs` namespace.

---

## Phase 9: Cleanup

### Test 9.1: Stop Services

**[CLAUDE]** Stop all observatory services.

```bash
# If running in foreground, Ctrl+C
# If running in background:
pkill -f "process-compose" 2>/dev/null || true
pkill -f "metta observatory" 2>/dev/null || true
echo "Services stopped"
```

---

### Test 9.2: Stop PostgreSQL

**[CLAUDE]** Stop the postgres container.

```bash
metta observatory postgres down
```

---

### Test 9.3: Clean K8s Resources

**[CLAUDE]** Remove the jobs namespace.

```bash
metta observatory local-k8s clean
```

---

## Quick Smoke Test

For a fast verification that everything works, run these commands in order:

**[CLAUDE]** Infrastructure check:

```bash
python -c "from metta.setup.tools.observatory.local_k8s import _is_running_in_container, detect_k8s_runtime; print(f'Container: {_is_running_in_container()}, Runtime: {detect_k8s_runtime()}')"
```

**[CLAUDE]** K8s connectivity:

```bash
KUBECONFIG=~/.kube/config-container kubectl --context orbstack cluster-info 2>&1 | head -1
```

**[CLAUDE]** Start and test services:

```bash
metta observatory postgres up -d --wait
metta observatory local-k8s status
```

**[HUMAN]** Full UI test:

```bash
metta observatory up
# Then open http://localhost:5173 in browser
```

---

## Test Results Template

When running this test plan, record results in this format:

```
Observatory Devcontainer Test Results
Date: YYYY-MM-DD
Tester: [Name / Claude Code]

Phase 1: Infrastructure
  1.1 Container Detection:    [ ] PASS  [ ] FAIL
  1.2 Docker Socket:          [ ] PASS  [ ] FAIL
  1.3 Kubeconfig Mount:       [ ] PASS  [ ] FAIL
  1.4 Tools Installed:        [ ] PASS  [ ] FAIL

Phase 2: Network
  2.1 DNS Resolution:         [ ] PASS  [ ] FAIL
  2.2 K8s API Reachable:      [ ] PASS  [ ] FAIL

Phase 3: Kubeconfig
  3.1 Config Generation:      [ ] PASS  [ ] FAIL
  3.2 Config Content:         [ ] PASS  [ ] FAIL
  3.3 kubectl Works:          [ ] PASS  [ ] FAIL

Phase 4: Runtime
  4.1 Runtime Detection:      [ ] PASS  [ ] FAIL
  4.2 Status Command:         [ ] PASS  [ ] FAIL

Phase 5: Database
  5.1 DB URI Detection:       [ ] PASS  [ ] FAIL
  5.2 Postgres Start:         [ ] PASS  [ ] FAIL
  5.3 Postgres Reachable:     [ ] PASS  [ ] FAIL
  5.4 DB Connection:          [ ] PASS  [ ] FAIL

Phase 6: Environment
  6.1 Env Variables:          [ ] PASS  [ ] FAIL

Phase 7: Services
  7.1 Backend Startup:        [ ] PASS  [ ] FAIL
  7.2 Port from Host:         [ ] PASS  [ ] FAIL  [HUMAN]

Phase 8: Integration
  8.1 Observatory Up:         [ ] PASS  [ ] FAIL
  8.2 Web UI Access:          [ ] PASS  [ ] FAIL  [HUMAN]
  8.3 K8s Namespace:          [ ] PASS  [ ] FAIL
  8.4 K8s from Services:      [ ] PASS  [ ] FAIL

Notes:
[Any issues encountered or observations]
```

---

## Troubleshooting Quick Reference

| Symptom                            | Likely Cause         | Test to Run         |
| ---------------------------------- | -------------------- | ------------------- |
| "Not in container"                 | Detection failed     | Test 1.1            |
| "docker: command not found"        | Tools missing        | Test 1.4            |
| "connection refused" to K8s        | Network/config issue | Tests 2.1, 2.2, 3.3 |
| "x509: certificate" error          | TLS config wrong     | Test 3.2            |
| "connection refused" to postgres   | Postgres not on host | Tests 5.2, 5.3      |
| "could not connect to server"      | Wrong DB URI         | Test 5.1            |
| Can't access from browser          | Port forwarding      | Test 7.2            |
| Runtime shows "k3d" not "orbstack" | Detection order      | Test 4.1            |
