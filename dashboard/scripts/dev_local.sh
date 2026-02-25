#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat << 'EOF'
Usage:
  dashboard/scripts/dev_local.sh

Runs dashboard against production read-only DB via k8s tunnel.
EOF
  exit 0
fi

if ! command -v pnpm > /dev/null 2>&1; then
  echo "ERROR: 'pnpm' command not found." >&2
  exit 1
fi
if ! command -v aws > /dev/null 2>&1; then
  echo "ERROR: 'aws' command not found." >&2
  exit 1
fi
if ! command -v kubectl > /dev/null 2>&1; then
  echo "ERROR: 'kubectl' command not found." >&2
  exit 1
fi

export DASHBOARD_DEV_AUTH_BYPASS="${DASHBOARD_DEV_AUTH_BYPASS:-true}"
export DASHBOARD_HOST="${DASHBOARD_HOST:-127.0.0.1}"
export DASHBOARD_PORT="${DASHBOARD_PORT:-8010}"
export NEXT_PUBLIC_DASHBOARD_API_BASE_URL="${NEXT_PUBLIC_DASHBOARD_API_BASE_URL:-http://127.0.0.1:8010}"

echo "[dashboard] Using live read-only DB mode via observatory k8s tunnel..."
RO_URI="${RO_URI:-$(aws secretsmanager get-secret-value --secret-id observatory/readonly-db-uri --query SecretString --output text)}"
RO_HOST="$(
  python - "$RO_URI" << 'PY'
import sys
from urllib.parse import urlparse
print(urlparse(sys.argv[1]).hostname or "")
PY
)"
if [[ -z "$RO_HOST" ]]; then
  echo "ERROR: Could not parse host from RO URI." >&2
  exit 1
fi

create_ro_proxy_pod() {
  kubectl -n observatory run ro-db-proxy --image=alpine/socat --restart=Never --command -- \
    sh -c "socat TCP-LISTEN:5432,fork,reuseaddr TCP:${RO_HOST}:5432"
  CREATED_PROXY_POD=1
}

if ! kubectl -n observatory get pod ro-db-proxy > /dev/null 2>&1; then
  create_ro_proxy_pod
else
  EXISTING_PROXY_SPEC="$(kubectl -n observatory get pod ro-db-proxy -o jsonpath='{.spec.containers[0].command} {.spec.containers[0].args}' 2> /dev/null || true)"
  if [[ "$EXISTING_PROXY_SPEC" != *"TCP:${RO_HOST}:5432"* ]]; then
    echo "[dashboard] Recreating ro-db-proxy for target host ${RO_HOST}..."
    kubectl -n observatory delete pod ro-db-proxy --ignore-not-found=true > /dev/null 2>&1 || true
    create_ro_proxy_pod
  else
    CREATED_PROXY_POD=0
  fi
fi
kubectl -n observatory wait --for=condition=Ready pod/ro-db-proxy --timeout=120s

kubectl -n observatory port-forward pod/ro-db-proxy 15432:5432 > /tmp/dashboard-ro-port-forward.log 2>&1 &
PORT_FORWARD_PID=$!

check_tunnel_ready() {
  if command -v nc > /dev/null 2>&1; then
    nc -z 127.0.0.1 15432 > /dev/null 2>&1
    return
  fi
  python - << 'PY'
import socket
sock = socket.socket()
sock.settimeout(0.2)
try:
    sock.connect(("127.0.0.1", 15432))
except OSError:
    raise SystemExit(1)
finally:
    sock.close()
PY
}

for _ in $(seq 1 30); do
  if check_tunnel_ready; then
    break
  fi
  sleep 1
done
if ! check_tunnel_ready; then
  echo "ERROR: Timed out waiting for local port 15432 tunnel." >&2
  exit 1
fi

export STATS_DB_READ_ONLY_URI="$(
  python - "$RO_URI" << 'PY'
import sys
from urllib.parse import quote, urlparse, urlunparse
u = urlparse(sys.argv[1])
if not u.scheme:
    raise SystemExit("Invalid read-only DB URI (missing scheme)")

userinfo = ""
if u.username is not None:
    user = quote(u.username, safe="")
    if u.password is not None:
        password = quote(u.password, safe="")
        userinfo = f"{user}:{password}@"
    else:
        userinfo = f"{user}@"

print(urlunparse(u._replace(netloc=f"{userinfo}127.0.0.1:15432")))
PY
)"

echo "[dashboard] Backend:  http://${DASHBOARD_HOST}:${DASHBOARD_PORT}"
echo "[dashboard] Frontend: http://127.0.0.1:5174"
echo "[dashboard] API base: ${NEXT_PUBLIC_DASHBOARD_API_BASE_URL}"
echo "[dashboard] DB mode: live-ro"

cleanup() {
  if [[ -n "${FRONTEND_PID:-}" ]]; then
    kill "$FRONTEND_PID" > /dev/null 2>&1 || true
  fi
  if [[ -n "${BACKEND_PID:-}" ]]; then
    kill "$BACKEND_PID" > /dev/null 2>&1 || true
  fi
  if [[ -n "${PORT_FORWARD_PID:-}" ]]; then
    kill "$PORT_FORWARD_PID" > /dev/null 2>&1 || true
  fi
  if [[ "${CREATED_PROXY_POD:-0}" == "1" ]]; then
    kubectl -n observatory delete pod ro-db-proxy --ignore-not-found=true > /dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

uv run python -m dashboard.backend.dashboard_backend.main &
BACKEND_PID=$!

pnpm --dir dashboard/frontend dev &
FRONTEND_PID=$!

wait -n "$BACKEND_PID" "$FRONTEND_PID"
STATUS=$?
exit "$STATUS"
