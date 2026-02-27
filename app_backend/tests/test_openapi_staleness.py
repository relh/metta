import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from fastapi.openapi.utils import get_openapi

from metta.app_backend.server import create_app

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

_OBSERVATORY_DIR = _REPO_ROOT / "web" / "observatory"
_OBSERVATORY_SCHEMA_DTS = _OBSERVATORY_DIR / "src" / "lib" / "api" / "generated" / "schema.d.ts"
_OBSERVATORY_OPENAPI_TS_BIN = _OBSERVATORY_DIR / "node_modules" / ".bin" / "openapi-typescript"
_OBSERVATORY_PRETTIER_BIN = _OBSERVATORY_DIR / "node_modules" / ".bin" / "prettier"

_SOFTMAX_DIR = _REPO_ROOT / "web" / "softmax.com"
_SOFTMAX_SCHEMA_DTS = _SOFTMAX_DIR / "src" / "lib" / "api" / "generated" / "schema.d.ts"
_SOFTMAX_OPENAPI_TS_BIN = _SOFTMAX_DIR / "node_modules" / ".bin" / "openapi-typescript"
_SOFTMAX_PRETTIER_BIN = _SOFTMAX_DIR / "node_modules" / ".bin" / "prettier"


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
