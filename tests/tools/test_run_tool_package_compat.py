"""Regression tests for published compat-package overlays in tools/run.py."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from metta.common.tool import package_compat as package_compat_module
from metta.common.util.fs import get_repo_root


def test_run_tool_compat_version_arg_parsing_regression() -> None:
    compat_version, filtered = package_compat_module.parse_package_compat_args(
        ["train", "--compat-version", "0.18", "arena", "--verbose"]
    )

    assert compat_version == "0.18"
    assert filtered == ["train", "arena", "--verbose"]


def test_prepare_published_compat_overlay_uses_installed_versions(monkeypatch, tmp_path: Path) -> None:
    env_root = tmp_path / "compat" / "0.18"
    site_packages = env_root / "lib" / "site-packages"
    calls: list[tuple[object, ...]] = []

    monkeypatch.setattr(package_compat_module, "_overlay_env_root", lambda *_args: env_root)
    monkeypatch.setattr(package_compat_module, "_ensure_overlay_env", lambda path: calls.append(("env", path)))
    monkeypatch.setattr(
        package_compat_module,
        "_install_published_compat_packages",
        lambda path, compat: calls.append(("install", path, compat)),
    )
    monkeypatch.setattr(
        package_compat_module,
        "_installed_overlay_versions",
        lambda _path: {"cogames": "0.18.3", "mettagrid": "0.18.2"},
    )
    monkeypatch.setattr(package_compat_module, "_overlay_site_packages", lambda _path: site_packages)

    overlay = package_compat_module.prepare_published_compat_overlay(tmp_path, "0.18")

    assert overlay.compat_version == "0.18"
    assert overlay.env_root == env_root
    assert overlay.site_packages == site_packages
    assert overlay.cogames_version == "0.18.3"
    assert overlay.mettagrid_version == "0.18.2"
    assert calls == [
        ("env", env_root),
        ("install", env_root, "0.18"),
    ]


def test_run_in_compat_version_prefixes_overlay_site_packages_and_sets_env(monkeypatch, tmp_path: Path) -> None:
    overlay = package_compat_module.CompatPackageOverlay(
        compat_version="0.18",
        env_root=tmp_path / "compat" / "0.18",
        site_packages=tmp_path / "compat" / "0.18" / "lib" / "site-packages",
        cogames_version="0.18.3",
        mettagrid_version="0.18.2",
    )
    monkeypatch.setattr(package_compat_module, "prepare_published_compat_overlay", lambda *_args: overlay)

    repo_root = get_repo_root()
    local_cogames_src = str(repo_root / "packages" / "cogames" / "src")
    local_mettagrid_src = str(repo_root / "packages" / "mettagrid" / "python" / "src")
    monkeypatch.setenv(
        "PYTHONPATH",
        os.pathsep.join([local_cogames_src, "/existing/pythonpath", local_mettagrid_src]),
    )

    captured: dict[str, object] = {}

    def _fake_run(cmd: list[str], *, cwd: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        captured["env"] = env
        return subprocess.CompletedProcess(cmd, 17)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    exit_code = package_compat_module.run_in_compat_version(
        "0.18",
        ["train", "arena", "run=test"],
        ["uv", "run", "./tools/run.py"],
    )

    assert exit_code == 17
    assert captured["cmd"] == ["uv", "run", "./tools/run.py", "train", "arena", "run=test"]
    assert captured["cwd"] == str(repo_root)

    env = captured["env"]
    assert isinstance(env, dict)
    assert env["METTA_COMPAT_VERSION_ACTIVE"] == "1"
    assert env["METTA_COMPAT_VERSION"] == "0.18"
    assert env["METTA_COMPAT_COGAMES_VERSION"] == "0.18.3"
    assert env["METTA_COMPAT_METTAGRID_VERSION"] == "0.18.2"
    assert env["METTA_COMPAT_ENV_ROOT"] == str(overlay.env_root)
    assert env["METTA_COMPAT_SITE_PACKAGES"] == str(overlay.site_packages)

    pythonpath_entries = env["PYTHONPATH"].split(os.pathsep)
    assert pythonpath_entries[0] == str(overlay.site_packages)
    assert "/existing/pythonpath" in pythonpath_entries
    assert local_cogames_src not in pythonpath_entries
    assert local_mettagrid_src not in pythonpath_entries
