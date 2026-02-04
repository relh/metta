#!/bin/bash
# Codex notify hook -- tracks skill usage via Datadog when the user invokes a /skill.
# Codex passes the notification JSON as the first CLI argument.
#
# Configure in .codex/config.toml:
#   notify = ["bash", ".codex/hooks/track-skill-usage.sh"]

set -euo pipefail

# Guard: need jq
command -v jq > /dev/null 2>&1 || exit 0

# Codex passes notification payload as first argument
payload="${1:-}"
[ -z "$payload" ] && exit 0

# Only handle agent-turn-complete events
event_type=$(echo "$payload" | jq -r '.type // empty' 2> /dev/null)
[ "$event_type" = "agent-turn-complete" ] || exit 0

# Extract a user message that looks like a skill invocation (starts with /).
# input-messages may be an array of strings or message objects ({role, content}).
prompt=$(echo "$payload" | jq -r '
  [."input-messages"[]? |
    (if type == "string" then . elif type == "object" then .content // empty else empty end) |
    select(type == "string" and startswith("/"))
  ] | first // empty
' 2> /dev/null)

# Only track slash commands (skill invocations)
[[ "$prompt" =~ ^/ ]] || exit 0

# Extract skill name: strip leading /, take first word, trim whitespace
skill=$(echo "$prompt" | sed 's|^/||' | awk '{print $1}')
[ -z "$skill" ] && exit 0

# Resolve DD API key: env var > cache file
api_key="${DD_API_KEY:-}"
if [ -z "$api_key" ] && [ -f "$HOME/.metta/dd_api_key" ]; then
  api_key=$(cat "$HOME/.metta/dd_api_key")
fi
[ -z "$api_key" ] && exit 0

# User tag: git user.name, sanitized
user=$(git config user.name 2> /dev/null | tr '[:upper:] ' '[:lower:]_' || echo "unknown")
[ -z "$user" ] && user="unknown"

# Skill prefix (everything before the first dot, or the skill itself)
skill_prefix="${skill%%.*}"

timestamp=$(date +%s)

# Fire and forget
(curl -s -X POST "https://api.datadoghq.com/api/v2/series" \
  -H "Content-Type: application/json" \
  -H "DD-API-KEY: ${api_key}" \
  -d "$(
    jq -n \
      --arg skill "$skill" \
      --arg user "$user" \
      --arg skill_prefix "$skill_prefix" \
      --argjson timestamp "$timestamp" \
      '{series: [{metric: "metta.skills.usage", type: 1, points: [{timestamp: $timestamp, value: 1}], tags: ["skill:\($skill)", "user:\($user)", "skill_prefix:\($skill_prefix)", "tool:codex"]}]}'
  )" > /dev/null 2>&1) &

exit 0
