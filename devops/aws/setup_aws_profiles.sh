#!/bin/bash -e

RESET_CONFIG=false
while [[ $# -gt 0 ]]; do
  case $1 in
    --reset)
      RESET_CONFIG=true
      shift
      ;;
    *)
      echo "Usage: $0 [--reset]"
      exit 1
      ;;
  esac
done

SSO_SESSION="softmax-sso"
SSO_URL="https://softmaxx.awsapps.com/start/"
REGION="us-east-1"

# account_name account_id
ACCOUNTS=(
  "softmax      751442549699"
  "tournament   583928386201"
  "sandbox      015142856185"
)

setup_sso_profile() {
  local profile=$1 account_id=$2 role=$3
  aws configure set "profile.${profile}.sso_session" "$SSO_SESSION"
  aws configure set "profile.${profile}.sso_account_id" "$account_id"
  aws configure set "profile.${profile}.sso_role_name" "$role"
  aws configure set "profile.${profile}.region" "$REGION"
}

initialize_aws_config() {
  mkdir -p ~/.aws

  if ! grep -q "\[sso-session ${SSO_SESSION}\]" ~/.aws/config 2> /dev/null; then
    cat >> ~/.aws/config << EOF
[sso-session ${SSO_SESSION}]
sso_start_url = ${SSO_URL}
sso_region = ${REGION}
sso_registration_scopes = sso:account:access
EOF
  fi

  aws configure set profile.softmax-root.region "$REGION"
  aws configure set profile.softmax-root.output json

  for entry in "${ACCOUNTS[@]}"; do
    read -r name account_id <<< "$entry"
    setup_sso_profile "$name" "$account_id" PowerUserAccess
    setup_sso_profile "${name}-admin" "$account_id" AdministratorAccess
  done

  # Ensure AWS_PROFILE is exported in shell rc files
  for rc in "${ZDOTDIR:-$HOME}/.zshrc" "$HOME/.bashrc"; do
    if [ ! -f "$rc" ]; then
      mkdir -p "$(dirname "$rc")"
      touch "$rc"
    fi
    grep -q '^export AWS_PROFILE=' "$rc" 2> /dev/null || echo -e '\nexport AWS_PROFILE=softmax' >> "$rc"
  done

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

if [ "$RESET_CONFIG" = true ]; then
  rm -rf ~/.aws/
  mkdir -p ~/.aws
  echo "AWS configuration cleared."
fi

# In CI/Docker/test, just write config and exit
if [ -n "$METTA_TEST_ENV" ] || [ -n "$CI" ] || [ -f /.dockerenv ]; then
  initialize_aws_config
  echo "Login to AWS using: aws sso login --profile softmax"
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
  aws sso login --profile softmax || true
fi

if check_sso_token; then
  echo "SSO login successful."
else
  echo "WARNING: SSO login completed but valid token not found."
  exit 1
fi
