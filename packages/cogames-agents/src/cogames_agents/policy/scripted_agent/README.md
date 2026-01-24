# Scripted Agent Policies (cogames-agents)

This package hosts the scripted agent implementations used by CoGames. The full CLI-facing documentation lives in the
`cogames` package:

- `cogames docs scripted_agent`
- `packages/cogames/src/cogames/docs/SCRIPTED_AGENT.md`

## Contents

- BaselineAgent / BaselinePolicy
- UnclippingAgent / UnclippingPolicy
- TinyBaseline demo policy (short name: `tiny_baseline`)

## Quick usage

```python
from cogames_agents.policy.scripted_agent.baseline_agent import BaselinePolicy

policy = BaselinePolicy(env)
```

```bash
uv run cogames play --mission evals.diagnostic_radial -p class=baseline --cogs 1
```
