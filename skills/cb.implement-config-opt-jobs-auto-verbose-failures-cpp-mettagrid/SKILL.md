---
name: cb.implement-config-opt-jobs-auto-verbose-failures-cpp-mettagrid
description: 'Use when implementing config opt jobs auto verbose failures cpp mettagrid.'
---

# Implement Config Opt Jobs Auto Verbose Failures Cpp Mettagrid

## Trigger

- Primary: "implementing config opt jobs auto verbose failures cpp mettagrid"

## Workflow

- Define the config behavior and failure visibility requirements, including exact defaults and error surfaces.
- Implement in mettagrid/C++ pathways with near-zero overhead on the default fast path.
- Add tests for both valid and invalid config cases, including the expected verbose failure output.
- Validate with targeted mettagrid tests and a quick performance check to confirm no hot-loop regression.
