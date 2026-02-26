# release-cortexcore.yml reference

Workflow file:

- `.github/workflows/release-cortexcore.yml`

Manual dispatch inputs:

- `publish`: `yes` or `no` (default `yes`)
- `target`: `testpypi` or `pypi` (default `testpypi`)

Build/publish behavior:

- Builds from `packages/cortex` using `python -m build`.
- Publishes with `pypa/gh-action-pypi-publish`.
- `testpypi` uses `skip-existing: true`.
- `pypi` creates deployment records and publishes to production environment.

Recommended release practice:

- Run TestPyPI first.
- Publish to PyPI from `main` after merge.
