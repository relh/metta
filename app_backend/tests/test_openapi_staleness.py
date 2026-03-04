import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from fastapi.openapi.utils import get_openapi

from metta.app_backend.server import create_app

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_EXPORT_OPENAPI_SCRIPT = _REPO_ROOT / "app_backend" / "scripts" / "export_openapi.py"

_OBSERVATORY_DIR = _REPO_ROOT / "web" / "observatory"
_OBSERVATORY_SCHEMA_DTS = _OBSERVATORY_DIR / "src" / "lib" / "api" / "generated" / "schema.d.ts"
_OBSERVATORY_OPENAPI_TS_BIN = _OBSERVATORY_DIR / "node_modules" / ".bin" / "openapi-typescript"
_OBSERVATORY_PRETTIER_BIN = _OBSERVATORY_DIR / "node_modules" / ".bin" / "prettier"

_SOFTMAX_DIR = _REPO_ROOT / "web" / "softmax.com"
_SOFTMAX_SCHEMA_DTS = _SOFTMAX_DIR / "src" / "lib" / "api" / "generated" / "schema.d.ts"
_SOFTMAX_OPENAPI_TS_BIN = _SOFTMAX_DIR / "node_modules" / ".bin" / "openapi-typescript"
_SOFTMAX_PRETTIER_BIN = _SOFTMAX_DIR / "node_modules" / ".bin" / "prettier"

_COGAMES_GENERATE_SCRIPT = _REPO_ROOT / "packages" / "cogames" / "scripts" / "generate_models.py"
_COGAMES_GENERATED_MODELS = _REPO_ROOT / "packages" / "cogames" / "src" / "cogames" / "cli" / "generated_models.py"


def _hash_file(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def _generate_schema(spec_json: str, openapi_ts_bin: Path, prettier_bin: Path, cwd: Path, output: Path) -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, dir=str(cwd)) as f:
        f.write(spec_json)
        spec_path = Path(f.name)

    tmp_output = cwd / f".tmp_schema_{id(output)}.d.ts"
    try:
        result = subprocess.run(
            [str(openapi_ts_bin), str(spec_path), "-o", str(tmp_output)],
            capture_output=True,
            text=True,
            cwd=str(cwd),
        )
        assert result.returncode == 0, f"openapi-typescript failed:\n{result.stderr}\n{result.stdout}"

        if prettier_bin.exists():
            subprocess.run(
                [str(prettier_bin), "--write", str(tmp_output)],
                capture_output=True,
                text=True,
                cwd=str(cwd),
            )

        shutil.move(str(tmp_output), str(output))
    finally:
        spec_path.unlink(missing_ok=True)
        tmp_output.unlink(missing_ok=True)


def _generate_public_openapi(output_dir: Path) -> Path:
    result = subprocess.run(
        [sys.executable, str(_EXPORT_OPENAPI_SCRIPT), "--output", str(output_dir)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"export_openapi.py failed:\n{result.stderr}\n{result.stdout}"
    spec_path = output_dir / "openapi.json"
    assert spec_path.exists(), f"export_openapi.py did not write {spec_path}"
    return spec_path


def test_openapi_json_up_to_date():
    """Ensure export_openapi.py writes the same public spec as app.openapi()."""
    app = create_app()
    fresh_spec = json.dumps(app.openapi(), indent=2) + "\n"

    with tempfile.TemporaryDirectory() as tmpdir:
        exported_spec = _generate_public_openapi(Path(tmpdir))
        if exported_spec.read_text() != fresh_spec:
            pytest.fail("Public OpenAPI export is outdated. Run: uv run app_backend/scripts/export_openapi.py")


@pytest.mark.skipif(not _OBSERVATORY_OPENAPI_TS_BIN.exists(), reason="openapi-typescript not installed")
def test_observatory_schema_dts_up_to_date():
    app = create_app()
    internal_spec = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)

    with tempfile.TemporaryDirectory() as tmpdir:
        fresh_schema = Path(tmpdir) / "schema.d.ts"
        _generate_schema(
            json.dumps(internal_spec, indent=2) + "\n",
            _OBSERVATORY_OPENAPI_TS_BIN,
            _OBSERVATORY_PRETTIER_BIN,
            _OBSERVATORY_DIR,
            fresh_schema,
        )

        if not _OBSERVATORY_SCHEMA_DTS.exists():
            pytest.fail("schema.d.ts is missing. Run: metta dev generate-api-types")

        if _hash_file(_OBSERVATORY_SCHEMA_DTS) != _hash_file(fresh_schema):
            pytest.fail("schema.d.ts is outdated. Run: metta dev generate-api-types")


@pytest.mark.skipif(not _SOFTMAX_OPENAPI_TS_BIN.exists(), reason="openapi-typescript not installed")
def test_softmax_schema_dts_up_to_date():
    app = create_app()
    public_spec = app.openapi()

    with tempfile.TemporaryDirectory() as tmpdir:
        fresh_schema = Path(tmpdir) / "schema.d.ts"
        _generate_schema(
            json.dumps(public_spec, indent=2) + "\n",
            _SOFTMAX_OPENAPI_TS_BIN,
            _SOFTMAX_PRETTIER_BIN,
            _SOFTMAX_DIR,
            fresh_schema,
        )

        if not _SOFTMAX_SCHEMA_DTS.exists():
            pytest.fail("schema.d.ts is missing. Run: metta dev generate-api-types")

        if _hash_file(_SOFTMAX_SCHEMA_DTS) != _hash_file(fresh_schema):
            pytest.fail("schema.d.ts is outdated. Run: metta dev generate-api-types")


def _hash_content_ignoring_timestamp(path: Path) -> str:
    """Hash file content, ignoring the datamodel-codegen timestamp line."""
    lines = path.read_text().splitlines(keepends=True)
    stable = [line for line in lines if not line.startswith("#   timestamp:")]
    return hashlib.sha256("".join(stable).encode()).hexdigest()


def test_cogames_generated_models_up_to_date():
    """Fail if cogames generated_models.py has drifted from fresh backend OpenAPI.

    Invokes packages/cogames/scripts/generate_models.py with --output to a temp dir,
    so there is a single source of truth for codegen flags.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        openapi_path = _generate_public_openapi(Path(tmpdir))
        fresh_output = Path(tmpdir) / "generated_models.py"

        result = subprocess.run(
            [
                sys.executable,
                str(_COGAMES_GENERATE_SCRIPT),
                str(openapi_path),
                "--output",
                str(fresh_output),
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"generate_models.py failed:\n{result.stderr}"

        if not _COGAMES_GENERATED_MODELS.exists():
            pytest.fail("generated_models.py is missing. Run: metta dev generate-api-types")

        committed_hash = _hash_content_ignoring_timestamp(_COGAMES_GENERATED_MODELS)
        fresh_hash = _hash_content_ignoring_timestamp(fresh_output)
        if committed_hash != fresh_hash:
            shutil.copy(fresh_output, "/tmp/generated_models_fresh.py")
            pytest.fail(
                "generated_models.py is outdated. Run: metta dev generate-api-types\n"
                "Fresh output saved to /tmp/generated_models_fresh.py for inspection."
            )
