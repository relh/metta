# Style Guide

## Non-Negotiables

1. **WRITE THE MINIMAL CHANGE.** Write exactly the smallest, most concise diff that accomplishes the objective. Not one
   line more. No "while I'm here" cleanup. No drive-by refactors. No extra abstractions. The goal is the smallest
   correct change, period. Everything else is noise you're adding to the codebase.

2. **NO BAND-AIDS. FIX THE ROOT CAUSE.** If your fix looks like a hotfix, you're doing it wrong. Stop. Zoom the fuck
   out. Figure out how to make the change holistically. Fix the actual invariant, the actual abstraction. If you're
   adding a special case to handle some symptom, you've already failed. Find the real bug.

3. **NO BACKWARDS COMPATIBILITY. EVER.** Dear god never leave in backwards compatibility shims. All the code is broken—
   that's why you're here. What you are writing is the definitive new way that it will not be broken. Update every
   callsite. Delete the old path. The new way is the only way. Stop hoarding dead code "just in case."

4. **NO DEFENSIVE NONE CHECKS.** Dear god do not add checks for variables being None or some other idiotic corner case
   that never actually happens. The real fix is to look at the fucking callsites. Fix the actual invariant. Make it
   impossible at the type level. Stop papering over broken assumptions with guard clauses.

5. **NO DICT.GET FALLBACKS.** `dict.get(..., None)` is not defensive programming, it's bug laundering. You're hiding a
   failure and smearing it across the codebase to explode later. Access the key directly. If it's missing, crash. Crash
   early, crash hard, crash obviously. That's how you find bugs.

6. **NOTHING IS SACRED.** The code is not there for a reason. The whole codebase is broken—you are here to fix it. Not
   to tiptoe around it. Delete dead code. Rip out bad abstractions. If something is wrong, tear it out and make it
   right. No code is precious. No pattern is sacred. You're not a visitor, you're an exterminator.

## Philosophy

Write lean code that will be kept. Favor simplicity over completeness. Search before writing—the codebase likely has
something similar already.

## Python Style

- Type hints on all function parameters
- No docstrings unless behavior is non-obvious
- Absolute imports only (`from metta.x import Y`, not `from .x import Y`)
- Private members start with `_`
- Empty `__init__.py` files (except public packages that need exports)
- `Optional[X]` over `X | None`
- Top-level imports only (no inline `from x import Y` inside functions)
- Use `collections.defaultdict` instead of `dict.setdefault()`
- Self-documenting code: clear names over comments, only comment the "why"

### Imports

```python
from __future__ import annotations  # When needed for forward refs
from metta.common.types import X    # Shared types from types.py
```

Circular import? Extract types to `types.py` or use module import (`import x.y as y_mod`).

## CI and Linting

```bash
metta lint --fix
```

Runs all linters (ruff, mypy, prettier) with auto-fix. Run before pushing.

## Additional Style Guides

Some guidelines exist in STYLE_GUIDE.md files closer to the code they are relevant to.
