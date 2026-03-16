# cog-cognition

This workspace package contains optional cognition layers for Mettagrid policies.

The Python import root is `cog_cognition`.

It owns:

- planner and reaction gating
- reflection over structured memory records
- semantic-policy and planner evaluation harnesses
- interview-style probes and offline diagnostics over structured policy behavior

It sits above `mettagrid_sdk` and `cog_cyborg`.

This package is intentionally optional. The base cyborg runtime and semantic policy stack should still run without
planning, reflection, or evaluation helpers installed.
