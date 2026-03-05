#!/usr/bin/env bash
set -euo pipefail

POLICY_VERSION_ID="${1:-7e16ac5f-7fe6-4970-940c-acc2d6c29013}"
API_BASE_URL="${DASHBOARD_API_BASE_URL:-https://api.policy-dashboard.vibeservatory.softmax-research.net}"
ANALYSIS_API_KEY="${DASHBOARD_ANTHROPIC_API_KEY:-}"
AUTH_TOKEN="${DASHBOARD_AUTH_TOKEN:-${OBSERVATORY_AUTH_TOKEN:-}}"

if [[ -z "$AUTH_TOKEN" ]]; then
  if [[ -f "$HOME/.metta/config.yaml" ]]; then
    AUTH_TOKEN="$(
      python - << 'PY'
import pathlib
import yaml
path = pathlib.Path.home() / '.metta' / 'config.yaml'
try:
    cfg = yaml.safe_load(path.read_text()) or {}
except Exception:
    print('')
    raise SystemExit
print((cfg.get('observatory_tokens') or {}).get('https://api.observatory.softmax-research.net', '') or '')
PY
    )"
  fi
fi

if [[ -z "$AUTH_TOKEN" ]]; then
  echo "ERROR: missing auth token. Set DASHBOARD_AUTH_TOKEN (or OBSERVATORY_AUTH_TOKEN), or configure ~/.metta/config.yaml." >&2
  exit 2
fi

failures=0
warnings=0

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

request() {
  local method="$1"
  local path="$2"
  local body="${3:-}"
  local outfile="$4"
  local header_file="$tmpdir/headers.txt"
  local curl_args=(
    -sS
    -D "$header_file"
    -H "X-Auth-Token: $AUTH_TOKEN"
    -H "Content-Type: application/json"
    -X "$method"
  )
  if [[ -n "$ANALYSIS_API_KEY" ]]; then
    curl_args+=(-H "X-Anthropic-Api-Key: $ANALYSIS_API_KEY")
  fi
  if [[ -n "$body" ]]; then
    curl_args+=(--data "$body")
  fi
  curl "${curl_args[@]}" "$API_BASE_URL$path" > "$outfile"
  awk 'NR==1 {print $2}' "$header_file"
}

json_value() {
  local file="$1"
  local expr="$2"
  python - "$file" "$expr" << 'PY'
import json
import sys
from typing import Any

path, expr = sys.argv[1], sys.argv[2]
try:
    obj: Any = json.load(open(path))
except Exception:
    print('non-json')
    raise SystemExit(0)

if expr == 'policy':
    policy = obj.get('policy') if isinstance(obj, dict) else {}
    if isinstance(policy, dict):
        print(f"{policy.get('name','?')} v{policy.get('version','?')}")
    else:
        print('?')
elif expr == 'episodes':
    episodes = obj.get('episodes') if isinstance(obj, dict) else []
    print(len(episodes) if isinstance(episodes, list) else 0)
elif expr == 'rows':
    rows = obj.get('rows') if isinstance(obj, dict) else []
    print(len(rows) if isinstance(rows, list) else 0)
elif expr == 'runs':
    runs = obj.get('runs') if isinstance(obj, dict) else []
    print(len(runs) if isinstance(runs, list) else 0)
elif expr == 'detail':
    if isinstance(obj, dict):
        print(obj.get('detail', obj.get('message', '')))
    else:
        print('')
else:
    print('')
PY
}

print_row() {
  local check="$1"
  local result="$2"
  local detail="$3"
  printf '%-22s | %-5s | %s\n' "$check" "$result" "$detail"
}

echo "Vibeservatory Dashboard Live API Smoke"
echo "base_url=$API_BASE_URL"
echo "policy_version_id=$POLICY_VERSION_ID"
if [[ -n "$ANALYSIS_API_KEY" ]]; then
  echo "analysis_key=provided via DASHBOARD_ANTHROPIC_API_KEY"
else
  echo "analysis_key=not provided (expecting backend key or key-required response)"
fi
printf '%-22s | %-5s | %s\n' "Check" "State" "Detail"
printf '%s\n' "-----------------------+-------+------------------------------------------------------------"

# data
file_data="$tmpdir/data.json"
code="$(request GET "/dashboard/v1/policies/versions/$POLICY_VERSION_ID/data" '' "$file_data")"
if [[ "$code" == "200" ]]; then
  print_row "data endpoint" "PASS" "$(json_value "$file_data" policy), episodes=$(json_value "$file_data" episodes)"
else
  print_row "data endpoint" "FAIL" "code=$code detail=$(json_value "$file_data" detail)"
  failures=$((failures + 1))
fi

# role percentiles
file_roles="$tmpdir/roles.json"
code="$(request GET "/dashboard/v1/policies/versions/$POLICY_VERSION_ID/role-percentiles" '' "$file_roles")"
if [[ "$code" == "200" ]]; then
  rows="$(json_value "$file_roles" rows)"
  if [[ "$rows" == "0" ]]; then
    print_row "role-percentiles" "WARN" "rows=0 (no parse percentile data yet)"
    warnings=$((warnings + 1))
  else
    print_row "role-percentiles" "PASS" "rows=$rows"
  fi
else
  print_row "role-percentiles" "FAIL" "code=$code detail=$(json_value "$file_roles" detail)"
  failures=$((failures + 1))
fi

# diagnose runs
file_diag="$tmpdir/diagnose.json"
code="$(request GET "/dashboard/v1/cogames-diagnose/runs" '' "$file_diag")"
if [[ "$code" == "200" ]]; then
  runs="$(json_value "$file_diag" runs)"
  if [[ "$runs" == "0" ]]; then
    print_row "diagnose runs" "WARN" "runs=0 (no diagnose artifacts yet)"
    warnings=$((warnings + 1))
  else
    print_row "diagnose runs" "PASS" "runs=$runs"
  fi
else
  print_row "diagnose runs" "FAIL" "code=$code detail=$(json_value "$file_diag" detail)"
  failures=$((failures + 1))
fi

# analysis
file_analysis="$tmpdir/analysis.json"
code="$(request POST "/dashboard/v1/policies/versions/$POLICY_VERSION_ID/analysis" '{}' "$file_analysis")"
detail="$(json_value "$file_analysis" detail)"
if [[ "$code" == "200" ]]; then
  print_row "analysis" "PASS" "analysis endpoint returned content"
elif [[ "$detail" == *"X-Anthropic-Api-Key"* || "$detail" == *"ANTHROPIC_API_KEY"* || "$detail" == *"Anthropic API key"* ]]; then
  print_row "analysis" "WARN" "code=$code $detail"
  warnings=$((warnings + 1))
else
  print_row "analysis" "FAIL" "code=$code $detail"
  failures=$((failures + 1))
fi

echo
echo "summary: failures=$failures warnings=$warnings"
if [[ "$failures" -gt 0 ]]; then
  exit 1
fi
