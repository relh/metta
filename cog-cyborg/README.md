# cog-cyborg

This workspace package contains the hybrid in-cog runtime for Mettagrid policies.

The Python import root is `cog_cyborg`.

It owns:

- bounded `step(sdk)` execution
- provider and secret-resolution utilities
- artifacts, memory, reflection, planning, evals, and policy code

It sits above `mettagrid_sdk` and below any higher-level live policy or code-update loop.

`cog_cyborg` is not the owner of the semantic SDK contract or game skill summaries. Those belong in `mettagrid_sdk`.
This package should consume the SDK-owned surface and focus on live bundle execution, review, and policy rewriting.
