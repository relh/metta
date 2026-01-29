---
name: r.make-package
description:
  Use when creating a new Python package in packages/ that needs uv workspace registration, src layout, and standalone
  PyPI/git repo readiness
---

# Make Package

Scaffolds a new Python package in `packages/` with proper structure, registers it in the uv workspace, and ensures it
can function as a standalone git repo or PyPI package.

**Announce at start:** "Creating new package `<name>` in packages/."

## The Process

1. Gather package metadata (name, description, author, dependencies)
2. Create package directory structure
3. Register in root `pyproject.toml` workspace
4. Verify with `uv sync`

## Step 1: Gather Metadata

Determine from user input or ask:

| Field          | Required                   | Example                      |
| -------------- | -------------------------- | ---------------------------- |
| name           | yes                        | `my-package`                 |
| import name    | yes (if differs from name) | `my_package`                 |
| description    | yes                        | "A utility library for X"    |
| dependencies   | no                         | `["numpy", "pydantic>=2.0"]` |
| python version | no (default: `>=3.12`)     | `>=3.12`                     |
| license        | no (default: MIT)          | MIT                          |

The **PyPI name** is what goes in `[project] name` (used for `pip install`). The **import name** is the Python module
(used for `import`). Usually the import name is the PyPI name with hyphens replaced by underscores.

## Step 2: Create Package Structure

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
PKG_DIR="$REPO_ROOT/packages/<name>"
IMPORT_NAME="<import_name>"  # hyphens -> underscores

mkdir -p "$PKG_DIR/src/$IMPORT_NAME"
mkdir -p "$PKG_DIR/tests"
```

### 2a: pyproject.toml

```toml
[build-system]
requires = ["setuptools==80.9.0", "wheel==0.45.1"]
build-backend = "setuptools.build_meta"

[project]
name = "<pypi-name>"
version = "0.1.0"
description = "<description>"
readme = "README.md"
requires-python = ">=3.12"
license = { text = "MIT" }
dependencies = []

[project.urls]
Repository = "https://github.com/Metta-AI/metta/tree/main/packages/<name>"

[dependency-groups]
dev = ["pytest>=8.3.3", "pytest-cov>=6.1.1"]

[tool.setuptools.packages.find]
where = ["src"]
include = ["<import_name>", "<import_name>.*"]

[tool.setuptools]
include-package-data = true

[tool.setuptools.package-data]
<import_name> = ["py.typed"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

### 2b: src/<import_name>/**init**.py

```python
"""<Description>."""
```

### 2c: src/<import_name>/py.typed

Empty marker file for PEP 561 type checking support.

### 2d: .gitignore

```gitignore
__pycache__/
*.py[cod]
*.so
build/
dist/
*.egg-info/
.pytest_cache/
.coverage
htmlcov/
.DS_Store
```

### 2e: README.md

````markdown
# <name>

<description>

## Installation

```bash
pip install <pypi-name>
```
````

## Development

```bash
uv sync
uv run pytest
```

````

### 2f: LICENSE

Use MIT license text with current year and "Metta AI" as copyright holder.

### 2g: tests/__init__.py

Empty file.

## Step 3: Register in Workspace

Edit the **root** `pyproject.toml`:

1. Add to `[tool.uv.workspace] members`:
   ```toml
   "packages/<name>",
````

2. Add to `[tool.uv.sources]`:

   ```toml
   <pypi-name> = { workspace = true }
   ```

3. If the root project should depend on this package, add to `[project] dependencies`:
   ```toml
   "<pypi-name>",
   ```
   (Only if the user wants the root project to depend on it. Ask if unclear.)

## Step 4: Verify

```bash
cd "$REPO_ROOT"
uv sync
uv run python -c "import <import_name>; print('OK')"
```

If `uv sync` fails, check:

- Name conflicts with existing PyPI packages
- Typos in workspace member path
- Missing `src` in `[tool.setuptools.packages.find]`

## Quick Reference

| File                     | Purpose                              |
| ------------------------ | ------------------------------------ |
| `pyproject.toml`         | Package metadata, deps, build config |
| `src/<name>/__init__.py` | Package entry point                  |
| `src/<name>/py.typed`    | PEP 561 type marker                  |
| `.gitignore`             | Build/cache exclusions               |
| `README.md`              | Standalone documentation             |
| `LICENSE`                | MIT license                          |
| `tests/`                 | Test directory                       |
| Root `pyproject.toml`    | Workspace registration               |

## Integration

**Pairs with:** `sk.make-skill` (for creating skills that accompany packages)
