#!/usr/bin/env bash
# Seed the local Observatory postgres from the production RDS instance.
#
# How it works:
#   1. Extracts the DB connection string from the k8s secret in prod
#   2. Spins up a temporary postgres:17 pod in the prod EKS cluster
#   3. Runs pg_dump INSIDE the pod (writes to file, not streamed over kubectl exec)
#   4. kubectl cp's the dump file to your machine
#   5. pg_restore into local postgres
#
# Prerequisites:
#   - AWS CLI configured with access to the main EKS cluster
#   - kubectl installed
#   - Local postgres running (metta dev postgres up -d)
#
# Usage:
#   bash app_backend/scripts/seed_local_db.sh                     # full dump + restore
#   bash app_backend/scripts/seed_local_db.sh --skip-download     # reuse cached dump
#   bash app_backend/scripts/seed_local_db.sh --dump-file <path>  # use specific dump
#   bash app_backend/scripts/seed_local_db.sh --size-only         # just check prod DB size

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DUMP_DIR="${TMPDIR:-/tmp}/metta-db-dumps"

# Prod EKS
EKS_CLUSTER="main"
EKS_REGION="us-east-1"
K8S_NAMESPACE="observatory"
K8S_SECRET="observatory-backend-env"
K8S_SECRET_KEY="STATS_DB_URI"
TEMP_POD_IMAGE="postgres:17"

# Local DB — matches observatory CLI defaults (cli.py:66-69)
LOCAL_HOST="127.0.0.1"
LOCAL_PORT="${POSTGRES_PORT:-5432}"
LOCAL_USER="postgres"
LOCAL_PASSWORD="password"
LOCAL_DB="metta"

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

SKIP_DOWNLOAD=false
SIZE_ONLY=false
DUMP_FILE=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --skip-download)
      SKIP_DOWNLOAD=true
      shift
      ;;
    --size-only)
      SIZE_ONLY=true
      shift
      ;;
    --dump-file)
      DUMP_FILE="$2"
      shift 2
      ;;
    --port)
      LOCAL_PORT="$2"
      shift 2
      ;;
    --help | -h)
      echo "Usage: $0 [OPTIONS]"
      echo ""
      echo "Seed local Observatory postgres from production RDS."
      echo ""
      echo "Options:"
      echo "  --skip-download  Reuse the latest cached dump file"
      echo "  --dump-file PATH Use a specific dump file"
      echo "  --size-only      Just print the prod DB size and exit"
      echo "  --port PORT      Local postgres port (default: \$POSTGRES_PORT or 5432)"
      echo "  -h, --help       Show this help"
      echo ""
      echo "Note: Restored data contains S3 URIs pointing to prod buckets."
      echo "The local backend can serve the dashboard and API without resolving"
      echo "these URIs, but replay links etc. will not work locally."
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEMP_POD_NAME=""

cleanup() {
  if [[ -n "${TEMP_POD_NAME}" ]]; then
    echo "==> Cleaning up temporary pod ${TEMP_POD_NAME}..."
    kubectl --context="${PROD_CONTEXT}" -n "${K8S_NAMESPACE}" \
      delete pod "${TEMP_POD_NAME}" --ignore-not-found --wait=false 2> /dev/null || true
  fi
}
trap cleanup EXIT

ensure_eks_context() {
  echo "==> Ensuring EKS cluster access..."
  aws eks update-kubeconfig \
    --name "${EKS_CLUSTER}" \
    --region "${EKS_REGION}" \
    --alias "eks-${EKS_CLUSTER}" > /dev/null
  PROD_CONTEXT="eks-${EKS_CLUSTER}"
}

extract_db_uri() {
  echo "==> Extracting STATS_DB_URI from k8s secret..."
  PROD_DB_URI=$(kubectl --context="${PROD_CONTEXT}" -n "${K8S_NAMESPACE}" \
    get secret "${K8S_SECRET}" -o jsonpath="{.data.${K8S_SECRET_KEY}}" | base64 -d)

  if [[ -z "${PROD_DB_URI}" ]]; then
    echo "ERROR: Failed to extract STATS_DB_URI from secret"
    exit 1
  fi
  # Print host only (not credentials)
  echo "==> Got DB URI (host: $(echo "${PROD_DB_URI}" | sed 's|.*@\(.*\)/.*|\1|'))"
}

create_temp_pod() {
  TEMP_POD_NAME="pg-dump-$(whoami | tr '[:upper:]_.' '[:lower:]--')-$(date +%s)"

  echo "==> Creating temporary pod ${TEMP_POD_NAME}..."
  kubectl --context="${PROD_CONTEXT}" -n "${K8S_NAMESPACE}" \
    run "${TEMP_POD_NAME}" \
    --image="${TEMP_POD_IMAGE}" \
    --restart=Never \
    --command -- sleep 1800

  echo "==> Waiting for pod to be ready..."
  kubectl --context="${PROD_CONTEXT}" -n "${K8S_NAMESPACE}" \
    wait --for=condition=Ready "pod/${TEMP_POD_NAME}" --timeout=120s
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

PROD_CONTEXT=""
PROD_DB_URI=""

ensure_eks_context
extract_db_uri

# --size-only: just check how big the prod DB is and exit
if [[ "${SIZE_ONLY}" == "true" ]]; then
  create_temp_pod
  echo "==> Checking production database size..."
  kubectl --context="${PROD_CONTEXT}" -n "${K8S_NAMESPACE}" \
    exec "${TEMP_POD_NAME}" -- \
    psql "${PROD_DB_URI}" -c "
            SELECT pg_size_pretty(pg_database_size(current_database())) AS db_size;
            SELECT relname AS table_name,
                   pg_size_pretty(pg_total_relation_size(C.oid)) AS total_size,
                   to_char(reltuples, 'FM999,999,999') AS row_estimate
            FROM pg_class C
            LEFT JOIN pg_namespace N ON (N.oid = C.relnamespace)
            WHERE nspname = 'public' AND relkind = 'r'
            ORDER BY pg_total_relation_size(C.oid) DESC
            LIMIT 20;
        "
  exit 0
fi

# Determine dump path
mkdir -p "${DUMP_DIR}"

if [[ -n "${DUMP_FILE}" ]]; then
  DUMP_PATH="${DUMP_FILE}"
  if [[ ! -f "${DUMP_PATH}" ]]; then
    echo "ERROR: Dump file not found: ${DUMP_PATH}"
    exit 1
  fi
  echo "==> Using provided dump file: ${DUMP_PATH}"
elif [[ "${SKIP_DOWNLOAD}" == "true" ]]; then
  if [[ -L "${DUMP_DIR}/prod-metta-latest.dump" ]]; then
    DUMP_PATH="$(readlink "${DUMP_DIR}/prod-metta-latest.dump")"
    # Handle relative symlink
    if [[ ! "${DUMP_PATH}" = /* ]]; then
      DUMP_PATH="${DUMP_DIR}/${DUMP_PATH}"
    fi
  elif [[ -f "${DUMP_DIR}/prod-metta-latest.dump" ]]; then
    DUMP_PATH="${DUMP_DIR}/prod-metta-latest.dump"
  else
    echo "ERROR: No cached dump found. Run without --skip-download first."
    exit 1
  fi
  echo "==> Reusing cached dump: ${DUMP_PATH}"
else
  # Download fresh dump from prod
  TIMESTAMP=$(date +%Y%m%d-%H%M%S)
  DUMP_PATH="${DUMP_DIR}/prod-metta-${TIMESTAMP}.dump"
  POD_DUMP_PATH="/tmp/dump.dump"

  create_temp_pod

  # Check DB size first
  echo "==> Checking production database size..."
  kubectl --context="${PROD_CONTEXT}" -n "${K8S_NAMESPACE}" \
    exec "${TEMP_POD_NAME}" -- \
    psql "${PROD_DB_URI}" -t -A -c \
    "SELECT pg_size_pretty(pg_database_size(current_database()))"

  # pg_dump to file INSIDE the pod (avoids binary corruption over kubectl exec stdout)
  echo "==> Running pg_dump inside pod (this may take a few minutes)..."
  kubectl --context="${PROD_CONTEXT}" -n "${K8S_NAMESPACE}" \
    exec "${TEMP_POD_NAME}" -- \
    bash -c "pg_dump '${PROD_DB_URI}' --format=custom --no-owner --no-privileges --no-comments --exclude-table=k8s_events > ${POD_DUMP_PATH} && ls -lh ${POD_DUMP_PATH}"

  # Copy dump file from pod to local machine.
  # Using `exec cat` instead of `kubectl cp` — cp uses tar internally and is
  # flaky for large files (unexpected EOF). cat streams the raw binary reliably
  # since pg_dump already wrote to a file (no stderr mixing risk).
  echo "==> Copying dump file from pod..."
  kubectl --context="${PROD_CONTEXT}" -n "${K8S_NAMESPACE}" \
    exec "${TEMP_POD_NAME}" -- cat "${POD_DUMP_PATH}" > "${DUMP_PATH}"

  DUMP_SIZE=$(du -h "${DUMP_PATH}" | cut -f1)
  echo "==> Dump complete: ${DUMP_PATH} (${DUMP_SIZE})"

  # Update latest symlink
  ln -sf "$(basename "${DUMP_PATH}")" "${DUMP_DIR}/prod-metta-latest.dump"
fi

# ---------------------------------------------------------------------------
# Restore into local postgres
# ---------------------------------------------------------------------------
# Local postgres runs in Docker — use docker exec for all DB operations since
# pg client tools (pg_isready, dropdb, pg_restore, psql) aren't installed on
# the host. The dump file is mounted via `docker cp` into the container.

DOCKER_CONTAINER="app_backend-postgres-1"

echo "==> Checking local postgres..."
if ! docker exec "${DOCKER_CONTAINER}" pg_isready -U "${LOCAL_USER}" -q 2> /dev/null; then
  echo "ERROR: Local postgres container '${DOCKER_CONTAINER}' is not running."
  echo "Start it with: metta dev postgres up -d"
  exit 1
fi

echo "==> Copying dump file into postgres container..."
docker cp "${DUMP_PATH}" "${DOCKER_CONTAINER}:/tmp/dump.dump"

echo "==> Dropping and recreating local database '${LOCAL_DB}'..."
# Force-drop handles active connections (postgres 13+)
docker exec "${DOCKER_CONTAINER}" dropdb -U "${LOCAL_USER}" --if-exists --force "${LOCAL_DB}"
docker exec "${DOCKER_CONTAINER}" createdb -U "${LOCAL_USER}" "${LOCAL_DB}"

echo "==> Restoring dump into local postgres (this may take a minute)..."
docker exec "${DOCKER_CONTAINER}" pg_restore \
  -U "${LOCAL_USER}" \
  -d "${LOCAL_DB}" \
  --no-owner \
  --no-privileges \
  --single-transaction \
  /tmp/dump.dump

# Clean up dump from container
docker exec "${DOCKER_CONTAINER}" rm -f /tmp/dump.dump

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "==> Seed complete! Summary:"
docker exec "${DOCKER_CONTAINER}" psql -U "${LOCAL_USER}" -d "${LOCAL_DB}" -c "
    SELECT 'policies' AS table_name, COUNT(*) FROM policies
    UNION ALL SELECT 'policy_versions', COUNT(*) FROM policy_versions
    UNION ALL SELECT 'episodes', COUNT(*) FROM episodes
    UNION ALL SELECT 'episode_policies', COUNT(*) FROM episode_policies
    UNION ALL SELECT 'episode_policy_metrics', COUNT(*) FROM episode_policy_metrics
    UNION ALL SELECT 'job_requests', COUNT(*) FROM job_requests
    UNION ALL SELECT 'seasons', COUNT(*) FROM seasons
    UNION ALL SELECT 'pools', COUNT(*) FROM pools
    UNION ALL SELECT 'matches', COUNT(*) FROM matches
    ORDER BY table_name;
    "

echo ""
echo "==> Next steps:"
echo "   1. Start the backend:  metta dev up"
echo "   2. Open:               http://localhost:3002/observatory/policies"
echo "   3. Pick a policy version and open its dashboard"
echo ""
echo "Note: S3 URIs (replay links, data_uri) point to prod buckets and"
echo "will not resolve locally. Dashboard charts and tables work fine."
