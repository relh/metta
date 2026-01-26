# Style Guide

## Philosophy

Write lean code that will be kept. Favor simplicity over completeness.

## Working Principles

**Write less code.** A smaller change that doesn't fully achieve the goal is better than a larger change that does. The
goal is code that gets kept, not a messy MVP.

**Search before writing.** The codebase likely has something similar. Look for existing implementations first.

**Trust your environment.** Don't add defensive checks for conditions guaranteed by the project structure.

**Self-documenting code.** Clear names over comments. Only comment the "why", not the "what".

## Python Style

- Type hints on all function parameters
- No docstrings unless behavior is non-obvious
- Absolute imports only (`from metta.x import Y`, not `from .x import Y`)
- Private members start with `_`
- Empty `__init__.py` files (except public packages that need exports)
- `Optional[X]` over `X | None`
- Top-level imports only (no inline `from x import Y` inside functions)
- Use `collections.defaultdict` instead of `dict.setdefault()`

### Imports

```python
from __future__ import annotations  # When needed for forward refs
from metta.common.types import X    # Shared types from types.py
```

Circular import? Extract types to `types.py` or use module import (`import x.y as y_mod`).

## CI and Linting

When CI fails on lint issues, fix them with:

```bash
metta lint --fix
```

This runs all linters (ruff, mypy, prettier) with auto-fix. Run before pushing to ensure CI passes.

## What Not To Do

- Don't add error handling for impossible cases
- Don't create abstractions for one-time operations
- Don't add comments that restate the code
- Don't add backwards-compatibility shims for unused code
- Don't run lint/tests automatically (too slow)
- Prefer user-driven pushes. Only push to the remote when the user explicitly asks, or when a required workflow cannot
  proceed without a push. If unsure, ask.

## Additional style guides

Some guidelines exist in STYLE_GUIDE.md files closer to the code they are relevant to.
