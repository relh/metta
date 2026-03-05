#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <project-gid> [extra trainingboard ingest-asana args...]" >&2
  exit 1
fi

PROJECT_GID="$1"
shift

if [[ -z "${ASANA_TOKEN:-}" ]]; then
  echo "ASANA_TOKEN is required" >&2
  exit 1
fi

cd "$(dirname "$0")/.."
uv run trainingboard ingest-asana --project-gid "$PROJECT_GID" "$@"
