#!/usr/bin/env bash
set -euo pipefail

POLICY_VERSION_ID="${1:-7e16ac5f-7fe6-4970-940c-acc2d6c29013}"
DASHBOARD_URL="${DASHBOARD_URL:-https://vibeservatory.softmax-research.net/policy-dashboard}"
STORAGE_STATE_PATH="${DASHBOARD_STORAGE_STATE:-$HOME/.cache/vibeservatory-dashboard/storage-state.json}"
ARTIFACT_DIR="${DASHBOARD_SMOKE_ARTIFACT_DIR:-/tmp/vibeservatory-dashboard-ui-smoke-$(date +%Y%m%d-%H%M%S)}"

if [[ ! -f "$STORAGE_STATE_PATH" ]]; then
  echo "ERROR: missing storage state at $STORAGE_STATE_PATH" >&2
  echo "Capture one with:" >&2
  echo "  DASHBOARD_STORAGE_STATE=$STORAGE_STATE_PATH dashboard/scripts/capture_observatory_storage_state.sh" >&2
  exit 2
fi

mkdir -p "$ARTIFACT_DIR"

echo "Vibeservatory Dashboard Live UI Smoke"
echo "dashboard_url=$DASHBOARD_URL"
echo "policy_version_id=$POLICY_VERSION_ID"
echo "storage_state=$STORAGE_STATE_PATH"
echo "artifacts=$ARTIFACT_DIR"
printf '%-18s | %-5s | %s\n' "Tab" "State" "Detail"
printf '%s\n' "-------------------+-------+------------------------------------------------------------"

failures=0
warnings=0

run_tab() {
  local tab="$1"
  local selector="$2"
  local png="$ARTIFACT_DIR/${tab}.png"
  local har="$ARTIFACT_DIR/${tab}.har"
  local log="$ARTIFACT_DIR/${tab}.log"
  local url="${DASHBOARD_URL}?policyVersionId=${POLICY_VERSION_ID}&tab=${tab}"

  local result="PASS"
  if ! npx --yes playwright screenshot \
    --browser=chromium \
    --load-storage="$STORAGE_STATE_PATH" \
    --wait-for-selector="$selector" \
    --wait-for-timeout=1200 \
    --timeout=45000 \
    --save-har="$har" \
    "$url" "$png" > "$log" 2>&1; then
    result="FAIL"
  fi

  local api_failures="none"
  if [[ -f "$har" ]]; then
    api_failures="$(
      python - "$har" << 'PY'
import json
import sys

try:
    obj = json.load(open(sys.argv[1]))
except Exception:
    print('har-parse-failed')
    raise SystemExit(0)

hits = []
for entry in obj.get('log', {}).get('entries', []):
    req = entry.get('request', {})
    res = entry.get('response', {})
    url = req.get('url', '')
    status = res.get('status', 0)
    if '/dashboard/v1/' in url and isinstance(status, int) and status >= 400:
        suffix = url.split('/dashboard/v1/', 1)[-1]
        hits.append(f"{status}:{suffix}")

print('; '.join(hits) if hits else 'none')
PY
    )"
  fi

  local detail="api_failures=$api_failures, screenshot=$(basename "$png")"
  if [[ "$result" == "PASS" ]]; then
    if [[ "$api_failures" == "none" ]]; then
      printf '%-18s | %-5s | %s\n' "$tab" "$result" "$detail"
    else
      printf '%-18s | %-5s | %s\n' "$tab" "WARN" "$detail"
      warnings=$((warnings + 1))
    fi
  else
    local reason
    reason="$(sed -n '1,2p' "$log" | tr '\n' ' ' | sed 's/  */ /g')"
    printf '%-18s | %-5s | %s\n' "$tab" "$result" "$reason"
    failures=$((failures + 1))
  fi
}

run_tab overview 'h2:has-text("Outcome Summary")'
run_tab performance 'h2:has-text("Filters & Export")'
run_tab coordination 'h2:has-text("Teammate Breakdown")'
run_tab capabilities 'h2:has-text("Diagnose")'

echo
echo "summary: failures=$failures warnings=$warnings artifacts=$ARTIFACT_DIR"
if [[ "$failures" -gt 0 ]]; then
  exit 1
fi
