from pathlib import Path

from metta.trainingboard.local.backend.server import (
    _resolve_frontend_target,
    build_dashboard_for_state_dir,
    parse_args,
)


def test_parse_args_defaults() -> None:
    args = parse_args([])
    assert args.host == "127.0.0.1"
    assert args.port == 8877


def test_resolve_frontend_target_blocks_traversal(tmp_path: Path) -> None:
    static_root = tmp_path / "static"
    static_root.mkdir(parents=True)

    assert _resolve_frontend_target(static_root, "../secrets.txt") is None
    assert _resolve_frontend_target(static_root, "../static/app.js") is None
    assert _resolve_frontend_target(static_root, "app.js") == (static_root / "app.js").resolve()


def test_build_dashboard_for_state_dir_works_without_cache(tmp_path: Path) -> None:
    payload = build_dashboard_for_state_dir(tmp_path)
    assert "ranked_axes" in payload
    assert len(payload["ranked_axes"]) == 6
