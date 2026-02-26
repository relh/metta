---
name: cortexcore-release
description:
  Bump the cortexcore package version and trigger the GitHub Actions publish workflow (release-cortexcore.yml) for
  TestPyPI or PyPI. Use when asked to release cortexcore, bump packages/cortex version, or publish via GitHub Action.
---

# Cortex Release

Use this skill to prepare and publish `cortexcore` from this metta repository.

## Workflow

1. Confirm release target and version strategy.

- Prefer `testpypi` first, then `pypi`.
- Use `--bump patch` unless a specific version is requested.

2. Run the helper script.

```bash
python skills/cortexcore-release/scripts/release_cortexcore.py \
  --repo /path/to/metta \
  --bump patch \
  --target testpypi
```

Use an explicit version if needed:

```bash
python skills/cortexcore-release/scripts/release_cortexcore.py \
  --repo /path/to/metta \
  --version 0.1.7 \
  --target pypi \
  --ref main
```

3. Review and land version changes.

- Verify edits in:
  - `packages/cortex/pyproject.toml`
  - `uv.lock` (`[[package]] name = "cortexcore"` block)
- Commit and push the bump on the intended branch.

4. Verify workflow run and publish result.

- `gh run list --workflow release-cortexcore.yml --limit 5`
- `gh run view <run-id> --log`
- Check package index:
  - TestPyPI: `https://test.pypi.org/project/cortexcore/`
  - PyPI: `https://pypi.org/project/cortexcore/`

## Resources

- Script: `scripts/release_cortexcore.py`
- Reference: `references/release-cortexcore-workflow.md`
