#!/usr/bin/env bash
# eval_cogas.sh — Run cogas agent through local evaluation and report
# aligned.junction.held score.
#
# Usage:
#   ./scripts/eval_cogas.sh [OPTIONS]
#
# Examples:
#   ./scripts/eval_cogas.sh
#   ./scripts/eval_cogas.sh --episodes 20
#   ./scripts/eval_cogas.sh --params 'miner=2&aligner=4&scrambler=3'
#   ./scripts/eval_cogas.sh --policy role_py --episodes 10 --threshold 1000

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Defaults
POLICY="cogsguard"
MISSION="cogsguard_arena.basic"
EPISODES=10
STEPS=1000
SEED=42
PARAMS=""
THRESHOLD=1500
FORMAT_FLAG="--format json"

usage() {
  cat << 'USAGE'
Usage: eval_cogas.sh [OPTIONS]

Options:
  --policy POLICY     Policy short name (default: cogsguard)
  --episodes N        Number of episodes (default: 10)
  --steps N           Max steps per episode (default: 1000)
  --mission MISSION   Mission to evaluate (default: cogsguard_arena.basic)
  --params PARAMS     URI params (e.g. 'miner=2&aligner=4&scrambler=3')
  --threshold N       aligned.junction.held threshold (default: 1500)
  --seed SEED         RNG seed (default: 42)
  -h, --help          Show this help
USAGE
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --policy)
      POLICY="$2"
      shift 2
      ;;
    --episodes)
      EPISODES="$2"
      shift 2
      ;;
    --steps)
      STEPS="$2"
      shift 2
      ;;
    --mission)
      MISSION="$2"
      shift 2
      ;;
    --params)
      PARAMS="$2"
      shift 2
      ;;
    --threshold)
      THRESHOLD="$2"
      shift 2
      ;;
    --seed)
      SEED="$2"
      shift 2
      ;;
    -h | --help) usage ;;
    *)
      echo "Unknown option: $1"
      usage
      ;;
  esac
done

# Build policy URI
POLICY_URI="metta://policy/${POLICY}"
if [[ -n "$PARAMS" ]]; then
  POLICY_URI="${POLICY_URI}?${PARAMS}"
fi

echo "=== CoGas Eval ==="
echo "Policy:    $POLICY_URI"
echo "Mission:   $MISSION"
echo "Episodes:  $EPISODES"
echo "Steps:     $STEPS"
echo "Seed:      $SEED"
echo "Threshold: $THRESHOLD (aligned.junction.held)"
echo ""

# Run cogames scrimmage and capture JSON output
TMPOUT=$(mktemp)
trap 'rm -f "$TMPOUT"' EXIT

if ! cogames scrimmage \
  -m "$MISSION" \
  -p "$POLICY_URI" \
  -e "$EPISODES" \
  -s "$STEPS" \
  --seed "$SEED" \
  $FORMAT_FLAG \
  > "$TMPOUT" 2>&1; then
  echo "ERROR: cogames scrimmage failed"
  cat "$TMPOUT"
  exit 1
fi

# Parse metrics from JSON output
python3 - "$TMPOUT" "$THRESHOLD" << 'PYEOF'
import json, sys

tmpout = sys.argv[1]
threshold = float(sys.argv[2])

with open(tmpout) as f:
    data = json.load(f)

missions = data.get("missions", [])
if not missions:
    print("ERROR: No mission results in output")
    sys.exit(1)

mission = missions[0]
summary = mission.get("mission_summary", mission)
game_stats = summary.get("avg_game_stats", {})
policy_summaries = summary.get("policy_summaries", [])
policy = policy_summaries[0] if policy_summaries else {}
agent_metrics = policy.get("avg_agent_metrics", {})
per_ep = policy.get("per_episode_per_policy_avg_rewards", {})

# Extract key metrics
ajh = game_stats.get("aligned.junction.held")
ajg = game_stats.get("aligned.junction.gained")
hg = agent_metrics.get("heart.gained")
hl = agent_metrics.get("heart.lost")
timeouts = policy.get("action_timeouts")

if per_ep:
    vals = [v for v in per_ep.values() if v is not None]
    reward = sum(vals) / len(vals) if vals else agent_metrics.get("reward")
else:
    reward = agent_metrics.get("reward")

def fmt(v):
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.2f}"
    return str(v)

# Print summary table
print("=== Results ===")
print(f"  aligned.junction.held:   {fmt(ajh)}")
print(f"  aligned.junction.gained: {fmt(ajg)}")
print(f"  heart.gained:            {fmt(hg)}")
print(f"  heart.lost:              {fmt(hl)}")
print(f"  reward:                  {fmt(reward)}")
print(f"  action_timeouts:         {fmt(timeouts)}")
print()

# Threshold check
if ajh is not None and ajh < threshold:
    print(f"FAIL: aligned.junction.held ({fmt(ajh)}) < threshold ({threshold})")
    sys.exit(1)
elif ajh is None:
    print("WARN: aligned.junction.held not found in output")
    sys.exit(1)
else:
    print(f"PASS: aligned.junction.held ({fmt(ajh)}) >= threshold ({threshold})")
PYEOF
