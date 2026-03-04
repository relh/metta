#!/usr/bin/env -S uv run
"""Export OpenAPI specs (internal and public) to JSON files.

Usage:
    uv run app_backend/scripts/export_openapi.py
    uv run app_backend/scripts/export_openapi.py --output /tmp/fresh

Called by Observatory's `npm run generate-api-types` to produce the JSON
that openapi-typescript consumes.

To also regenerate Python models for cogames, run:
    metta dev generate-api-types
"""

import json
import sys
from pathlib import Path

from fastapi.openapi.utils import get_openapi

from metta.app_backend.server import create_app

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "src" / "metta" / "app_backend" / "generated"


def main() -> None:
    output_dir = DEFAULT_OUTPUT_DIR
    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        output_dir = Path(sys.argv[idx + 1])

    app = create_app()

    internal_spec = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
    )
    public_spec = app.openapi()

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "internal-openapi.json").write_text(json.dumps(internal_spec, indent=2) + "\n")
    (output_dir / "openapi.json").write_text(json.dumps(public_spec, indent=2) + "\n")

    internal_paths = len(internal_spec.get("paths", {}))
    public_paths = len(public_spec.get("paths", {}))
    print(f"Wrote specs to {output_dir}")
    print(f"  internal-openapi.json: {internal_paths} paths")
    print(f"  openapi.json: {public_paths} paths")


if __name__ == "__main__":
    main()
