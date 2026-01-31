---
name: n.add-publishable-package
description:
  Add a new publishable Python package to the monorepo. Guides through pyproject.toml setup, GitHub Actions workflow,
  PyPI trusted publisher, child repo, and publish.py integration. Use when creating a package that needs to be published
  to PyPI.
---

# Add a Publishable Package

Walk the user through every step. Many steps require manual action in GitHub/PyPI UIs -- prompt the user to complete
those and confirm before continuing.

For a detailed explanation of how the publish flow works end-to-end (orchestration, CI wait gates, dependency pinning),
see `metta/setup/tools/PUBLISHING.md`.

## Prerequisites

The package must already exist under `packages/{package}/` with source code and a basic `pyproject.toml`.

## Step 1: pyproject.toml -- setuptools_scm

Add dynamic versioning so the version is derived from git tags at build time.

**build-system requires** -- add `setuptools_scm==8.1.0`:

```toml
[build-system]
requires = ["setuptools==80.9.0", "wheel==0.45.1", "setuptools_scm==8.1.0"]
build-backend = "setuptools.build_meta"
```

**Remove static version**, add dynamic:

```toml
[project]
name = "{package}"
dynamic = ["version"]
```

**Add setuptools_scm config** (replace `{package}` with the actual name, using hyphens):

```toml
[tool.setuptools_scm]
tag_regex = "^{package}-v(?P<version>\\d+\\.\\d+\\.\\d+(?:\\.\\d+)?)$"
version_scheme = "no-guess-dev"
local_scheme = "no-local-version"
root = "../.."
fallback_version = "0.0.0"
git_describe_command = ["git", "describe", "--dirty", "--tags", "--long", "--match", "{package}-v*"]
```

**Verify**: `uvx --from build pyproject-build packages/{package}` should produce a wheel with version `0.0.post1.devN`.

## Step 2: GitHub Actions Release Workflow

Create `.github/workflows/release-{package}.yml`. Use `release-cogames-agents.yml` as a template for pure-Python
packages, or `release-mettagrid.yml` for packages needing compiled artifacts.

Key requirements:

- **Trigger**: `push.tags: {package}-v*` plus `workflow_dispatch` with `publish` and `target` inputs
- **Permissions**: `contents: read`, `id-token: write`, `deployments: write`
- **Build job**: `pip install --upgrade pip build twine setuptools_scm==8.1.0`, then `python -m build`, `twine check`
- **Publish job**: Uses `pypa/gh-action-pypi-publish@release/v1` with OIDC (no API tokens)
- **Environment**: `{package}-{pypi|testpypi}` (matches GitHub environment names from step 3)
- **Runner**: `blacksmith-2vcpu-ubuntu-2404` (or appropriate for the build)

Optional enhancements (see `release-cogames.yml` for examples):

- Deployment records via `actions/github-script`
- Wait-for-dependency job that polls PyPI until a dependency is available
- Smoke test job that installs from PyPI and runs basic checks

## Step 3: GitHub Environments (Manual -- Prompt User)

**Ask the user to create two GitHub environments** in the repo settings:

1. Go to https://github.com/Metta-AI/metta/settings/environments
2. Create environment `{package}-pypi`
3. Create environment `{package}-testpypi`

No secrets are needed -- authentication uses OIDC trusted publishers configured in step 4.

## Step 4: PyPI Trusted Publisher (Manual -- Prompt User)

**Ask the user to configure trusted publishers on both PyPI and TestPyPI.**

### PyPI (https://pypi.org)

If the project doesn't exist yet, use "pending publisher":

1. Go to https://pypi.org/manage/account/publishing/
2. Add a pending publisher:
   - PyPI project name: `{package}`
   - Owner: `Metta-AI`
   - Repository: `metta`
   - Workflow name: `release-{package}.yml`
   - Environment name: `{package}-pypi`

If the project already exists:

1. Go to https://pypi.org/manage/project/{package}/settings/publishing/
2. Add a new publisher with the same fields

### TestPyPI (https://test.pypi.org)

Same process but on test.pypi.org:

1. Go to https://test.pypi.org/manage/account/publishing/
2. Add pending publisher with environment name: `{package}-testpypi`

### Verify

Run the workflow manually targeting testpypi:

```
gh workflow run release-{package}.yml -f publish=yes -f target=testpypi
```

## Step 5: Register in publish.py

Add the package to `metta/setup/tools/publish.py` so `metta publish {package}` works.

1. **Add to Package enum**:

```python
class Package(StrEnum):
    ...
    YOUR_PACKAGE = "{package}"
```

2. **Add to workflow URL map**:

```python
_RELEASE_WORKFLOW_URL_FOR_PACKAGE = {
    ...
    Package.YOUR_PACKAGE: "https://github.com/Metta-AI/metta/actions/workflows/release-{package}.yml",
}
```

3. **Add orchestration logic** (if the package depends on other published packages):
   - Add a block in `_publish()` that offers to publish dependencies first
   - Add `{dep}_version_to_pin` parameters if dependency pinning is needed
   - Pattern: check `if package == Package.YOUR_PACKAGE and {dep}_version_to_pin is None`

## Step 6: Child Repository (Optional -- Prompt User)

If the package needs a standalone public repo at `github.com/Metta-AI/{package}`:

1. **Ask user to create** the repo on GitHub (empty, no README)
2. The `devops/git/push_child_repo.py` script handles syncing:
   - Filters monorepo git history to `packages/{package}/`
   - Makes the package directory the repo root
   - Force-pushes main branch and matching tags
3. Runs automatically during `metta publish` when `push_git_history_to_child_repo=True`

## Step 7: Test End-to-End

```bash
# Dry run the full publish flow
metta publish {package} --dry-run

# If it has dependencies, verify the orchestration order
metta publish {package} --dry-run --force
```

## Checklist

- [ ] `pyproject.toml` has `setuptools_scm` in build requires and `dynamic = ["version"]`
- [ ] `[tool.setuptools_scm]` section with correct tag_regex for the package name
- [ ] `.github/workflows/release-{package}.yml` created with correct tag trigger
- [ ] Workflow installs `setuptools_scm==8.1.0` in the build step
- [ ] GitHub environments `{package}-pypi` and `{package}-testpypi` created
- [ ] PyPI trusted publisher configured for `{package}-pypi` environment
- [ ] TestPyPI trusted publisher configured for `{package}-testpypi` environment
- [ ] Package added to `Package` enum in `publish.py`
- [ ] Package added to `_RELEASE_WORKFLOW_URL_FOR_PACKAGE`
- [ ] Orchestration logic added if package has publishable dependencies
- [ ] Child repo created and `push_child_repo.py` tested (if needed)
- [ ] `metta publish {package} --dry-run` works
- [ ] Manual workflow dispatch to testpypi succeeds
