#!/usr/bin/env bash
set -euo pipefail

STORAGE_STATE_PATH="${DASHBOARD_STORAGE_STATE:-$HOME/.cache/vibeservatory-dashboard/storage-state.json}"
DASHBOARD_URL="${DASHBOARD_URL:-https://vibeservatory.softmax-research.net/policy-dashboard}"

mkdir -p "$(dirname "$STORAGE_STATE_PATH")"

echo "Launching interactive browser login to capture storage state..."
echo "Target URL: $DASHBOARD_URL"
echo "Storage output: $STORAGE_STATE_PATH"
echo "After login is complete, close the browser window to finish capture."

npx --yes playwright open --browser=chromium --save-storage="$STORAGE_STATE_PATH" "$DASHBOARD_URL"

echo "Saved: $STORAGE_STATE_PATH"
