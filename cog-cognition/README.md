# cog-cognition

This workspace package contains optional cognition layers for Mettagrid policies.

The Python import root is `cog_cognition`.

It owns:

- planner and reaction gating
- reflection over structured memory records
- trajectory analysis, evaluation harnesses, and interview-style probes built on `cogames` and `mettagrid` tooling
- offline diagnostics over structured policy behavior

It sits above `cog_cyborg` for optional cognition layers and currently reaches into `cogames` and `mettagrid`
programmatic surfaces for offline analysis.

This package is intentionally optional. The base cyborg runtime and semantic policy stack do not require
`cog_cognition` to be installed, but the analysis modules here currently depend on the rollout and policy-loading
surfaces provided by `cogames` and `mettagrid`.
