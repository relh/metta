#!/bin/bash -e

RESET_CONFIG=false
FULL_RESET_CONFIG=false
while [[ $# -gt 0 ]]; do
  case $1 in
    --reset)
      RESET_CONFIG=true
      shift
      ;;
    --full-reset)
      FULL_RESET_CONFIG=true
      shift
      ;;
    *)
      echo "Usage: $0 [--reset] [--full-reset]"
      exit 1
      ;;
  esac
done

SSO_SESSION="softmax-sso"
SSO_URL="https://softmaxx.awsapps.com/start/"
REGION="us-east-1"
BEGIN_MARKER="# BEGIN softmax-managed"
END_MARKER="# END softmax-managed"

MANAGED_SSO_PROFILES=(
  "softmax 751442549699 PowerUserAccess"
  "softmax-admin 751442549699 AdministratorAccess"
  "contractor-softmax 751442549699 ContractorAccess"
  "tournament 583928386201 PowerUserAccess"
  "tournament-admin 583928386201 AdministratorAccess"
  "contractor-tournament 583928386201 ContractorAccess"
  "sandbox 015142856185 PowerUserAccess"
  "sandbox-admin 015142856185 AdministratorAccess"
  "contractor-sandbox 015142856185 ContractorAccess"
  "softmax-org 111005867451 AdministratorAccess"
  "polis-admin 901289084804 AdministratorAccess"
)

aws_config_path() {
  printf '%s\n' "${AWS_CONFIG_FILE:-$HOME/.aws/config}"
}

managed_section_headers() {
  local headers=("[sso-session ${SSO_SESSION}]" "[profile softmax-root]")

  for entry in "${MANAGED_SSO_PROFILES[@]}"; do
    read -r profile _ <<< "$entry"
    headers+=("[profile ${profile}]")
  done

  local IFS='|'
  printf '%s\n' "${headers[*]}"
}

strip_managed_config() {
  local config=$1 output=$2 managed_headers
  managed_headers=$(managed_section_headers)

  awk -v begin="$BEGIN_MARKER" -v end="$END_MARKER" -v managed_sections="$managed_headers" '
    BEGIN {
      split(managed_sections, managed, "|")
      for (i in managed) {
        if (managed[i] != "") {
          skip_headers[managed[i]] = 1
        }
      }
    }

    $0 == begin {skip_block = 1; next}
    $0 == end {skip_block = 0; next}
    skip_block {next}

    /^\[/ {skip_section = ($0 in skip_headers)}
    !skip_section {print}
  ' "$config" > "$output"
}

render_managed_block() {
  cat << EOF
[sso-session ${SSO_SESSION}]
sso_start_url = ${SSO_URL}
sso_region = ${REGION}
sso_registration_scopes = sso:account:access

[profile softmax-root]
region = ${REGION}
output = json
EOF

  for entry in "${MANAGED_SSO_PROFILES[@]}"; do
    read -r profile account_id role <<< "$entry"
    cat << EOF

[profile ${profile}]
sso_session = ${SSO_SESSION}
sso_account_id = ${account_id}
sso_role_name = ${role}
region = ${REGION}
EOF
  done
}

write_managed_config() {
  local config tmp
  config=$(aws_config_path)
  tmp=$(mktemp)
  mkdir -p "$(dirname "$config")"
  touch "$config"

  strip_managed_config "$config" "$tmp"

  {
    cat "$tmp"
    if [ -s "$tmp" ]; then
      printf '\n'
    fi
    printf '%s\n' "$BEGIN_MARKER"
    render_managed_block
    printf '\n%s\n' "$END_MARKER"
  } > "${tmp}.new"

  mv "${tmp}.new" "$config"
  rm -f "$tmp"
}

remove_managed_config() {
  local config tmp
  config=$(aws_config_path)
  tmp=$(mktemp)
  mkdir -p "$(dirname "$config")"
  touch "$config"

  strip_managed_config "$config" "$tmp"
  mv "$tmp" "$config"
}

ensure_default_profile_export() {
  local default_profile="${AWS_PROFILE_DEFAULT:-softmax}"

  for rc in "${ZDOTDIR:-$HOME}/.zshrc" "$HOME/.bashrc"; do
    if [ ! -f "$rc" ]; then
      mkdir -p "$(dirname "$rc")"
      touch "$rc"
    fi
    grep -q '^export AWS_PROFILE=' "$rc" 2> /dev/null || echo -e "\nexport AWS_PROFILE=${default_profile}" >> "$rc"
  done
}

initialize_aws_config() {
  write_managed_config
  ensure_default_profile_export
  echo "AWS profiles configured."
}

check_sso_token() {
  local cache_dir=~/.aws/sso/cache
  [ -d "$cache_dir" ] || return 1

  for token_file in "$cache_dir"/*.json; do
    [ -f "$token_file" ] || continue
    grep -q "softmaxx.awsapps.com" "$token_file" 2> /dev/null || continue

    local expiration
    expiration=$(grep -o '"expiresAt": "[^"]*"' "$token_file" | cut -d '"' -f 4)
    [ -n "$expiration" ] || continue

    local expiry_ts
    expiry_ts=$(date -d "$expiration" +%s 2> /dev/null || date -j -f "%Y-%m-%dT%H:%M:%SZ" "$expiration" +%s 2> /dev/null)
    [ -n "$expiry_ts" ] && [ "$(date +%s)" -lt "$expiry_ts" ] && return 0
  done
  return 1
}

if [ "$FULL_RESET_CONFIG" = true ]; then
  rm -rf ~/.aws/
  mkdir -p ~/.aws
  echo "AWS configuration fully cleared."
elif [ "$RESET_CONFIG" = true ]; then
  remove_managed_config
  echo "Managed AWS configuration cleared."
fi

# In CI/Docker/test, just write config and exit
if [ -n "$METTA_TEST_ENV" ] || [ -n "$CI" ] || [ -f /.dockerenv ]; then
  initialize_aws_config
  echo "Login to AWS using: aws sso login --profile ${AWS_PROFILE_DEFAULT:-softmax}"
  exit 0
fi

initialize_aws_config

if check_sso_token; then
  echo "Valid SSO token already exists."
  exit 0
fi

if [ -n "$AWS_SSO_NONINTERACTIVE" ]; then
  echo "Skipping interactive 'aws sso login' due to AWS_SSO_NONINTERACTIVE"
else
  aws sso login --profile "${AWS_PROFILE_DEFAULT:-softmax}" || true
fi

if check_sso_token; then
  echo "SSO login successful."
else
  echo "WARNING: SSO login completed but valid token not found."
  exit 1
fi
