import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

import pytest
from fastapi.openapi.utils import get_openapi

from metta.app_backend.server import create_app

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_OBSERVATORY_DIR = _REPO_ROOT / "web" / "observatory"
_SCHEMA_DTS = _OBSERVATORY_DIR / "src" / "lib" / "api" / "generated" / "schema.d.ts"
_OPENAPI_TS_BIN = _OBSERVATORY_DIR / "node_modules" / ".bin" / "openapi-typescript"


def _hash_file(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


@pytest.mark.skipif(not _OPENAPI_TS_BIN.exists(), reason="openapi-typescript not installed")
def test_schema_dts_up_to_date():
    app = create_app()
    internal_spec = get_openapi(title=app.title, version=app.version, routes=app.routes)

    with tempfile.TemporaryDirectory() as tmpdir:
        spec_path = Path(tmpdir) / "internal-openapi.json"
        spec_path.write_text(json.dumps(internal_spec, indent=2) + "\n")

        fresh_schema = Path(tmpdir) / "schema.d.ts"
        result = subprocess.run(
            [str(_OPENAPI_TS_BIN), str(spec_path), "-o", str(fresh_schema)],
            capture_output=True,
            text=True,
            cwd=str(_OBSERVATORY_DIR),
        )
        assert result.returncode == 0, f"openapi-typescript failed:\n{result.stderr}\n{result.stdout}"

        if not _SCHEMA_DTS.exists():
            pytest.fail("schema.d.ts is missing. Run: cd web/observatory && npm run generate-api-types")

        if _hash_file(_SCHEMA_DTS) != _hash_file(fresh_schema):
            pytest.fail("schema.d.ts is outdated. Run: cd web/observatory && npm run generate-api-types")
