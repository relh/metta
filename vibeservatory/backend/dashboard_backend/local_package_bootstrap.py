from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def ensure_repo_src_on_path(relative_src: str) -> Path:
    src_root = REPO_ROOT / relative_src
    if not src_root.is_dir():
        raise RuntimeError(f"Expected local source directory is missing: {src_root}")

    src_root_str = str(src_root)
    if src_root_str not in sys.path:
        sys.path.append(src_root_str)
    return src_root
