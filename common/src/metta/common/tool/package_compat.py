from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from metta.common.compat_version import parse_compat_version
from metta.common.util.fs import get_repo_root

_LOCAL_PACKAGE_PATHS = (
    Path("packages/cogames/src"),
    Path("packages/mettagrid/python/src"),
)
_INSTALLED_VERSIONS_QUERY = """
import importlib.metadata
import json


def version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


print(json.dumps({"cogames": version("cogames"), "mettagrid": version("mettagrid")}))
"""
_PURELIB_QUERY = """
import sysconfig

print(sysconfig.get_path("purelib"))
"""
_WORKSPACE_SOURCE_DIR_CANDIDATES = (
    Path("src"),
    Path("python") / "src",
)
_PUBLISHED_COMPAT_PACKAGES = ("cogames", "mettagrid")
_OVERLAY_LAYOUT_VERSION = "2"


@dataclass(frozen=True)
class CompatPackageOverlay:
    compat_version: str
    env_root: Path
    site_packages: Path
    cogames_version: str
    mettagrid_version: str


def parse_package_compat_args(argv: list[str]) -> tuple[str | None, list[str]]:
    filtered: list[str] = []
    compat_version: str | None = None
    idx = 0
    while idx < len(argv):
        arg = argv[idx]
        if arg in {"--compat-version", "--compat_version"}:
            if idx + 1 >= len(argv):
                raise ValueError("--compat-version requires a value")
            compat_version = argv[idx + 1]
            idx += 2
            continue
        if arg.startswith("--compat-version=") or arg.startswith("--compat_version="):
            compat_version = arg.split("=", 1)[1]
            idx += 1
            continue
        filtered.append(arg)
        idx += 1
    return compat_version, filtered


def _normalize_compat_version(raw_compat_version: str) -> str:
    compat_version = parse_compat_version(raw_compat_version)
    if compat_version is None or compat_version != raw_compat_version:
        raise ValueError(f"Compat version '{raw_compat_version}' must use X.Y format.")
    return compat_version


def _overlay_env_root(repo_root: Path | str, compat_version: str) -> Path:
    repo_root = Path(repo_root)
    safe_version = re.sub(r"[^A-Za-z0-9_.-]+", "_", compat_version).strip("_")
    return repo_root / ".metta" / "compat_packages" / safe_version


def _overlay_python(env_root: Path) -> Path:
    if os.name == "nt":
        return env_root / "Scripts" / "python.exe"
    return env_root / "bin" / "python"


def _overlay_layout_marker(env_root: Path) -> Path:
    return env_root / ".metta_overlay_layout"


def _overlay_layout_is_current(env_root: Path) -> bool:
    marker = _overlay_layout_marker(env_root)
    if not marker.exists():
        return False
    return marker.read_text().strip() == _OVERLAY_LAYOUT_VERSION


def _ensure_overlay_env(env_root: Path) -> None:
    python_path = _overlay_python(env_root)
    if python_path.exists() and _overlay_layout_is_current(env_root):
        return

    if env_root.exists():
        shutil.rmtree(env_root)

    env_root.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("uv"):
        subprocess.run(
            ["uv", "venv", "--python", sys.executable, str(env_root)],
            check=True,
            cwd=str(get_repo_root()),
        )
        _overlay_layout_marker(env_root).write_text(_OVERLAY_LAYOUT_VERSION)
        return

    subprocess.run(
        [sys.executable, "-m", "venv", str(env_root)],
        check=True,
        cwd=str(get_repo_root()),
    )
    _overlay_layout_marker(env_root).write_text(_OVERLAY_LAYOUT_VERSION)


def _run_overlay_python(env_root: Path, code: str) -> str:
    python_path = _overlay_python(env_root)
    result = subprocess.run(
        [str(python_path), "-c", code],
        check=True,
        capture_output=True,
        text=True,
        cwd=str(get_repo_root()),
    )
    return result.stdout.strip()


def _installed_overlay_versions(env_root: Path) -> dict[str, str | None]:
    python_path = _overlay_python(env_root)
    if not python_path.exists():
        return {"cogames": None, "mettagrid": None}
    output = _run_overlay_python(env_root, _INSTALLED_VERSIONS_QUERY)
    loaded = json.loads(output)
    return {
        "cogames": loaded.get("cogames"),
        "mettagrid": loaded.get("mettagrid"),
    }


def _overlay_site_packages(env_root: Path) -> Path:
    return Path(_run_overlay_python(env_root, _PURELIB_QUERY))


def _install_published_compat_packages(env_root: Path, compat_version: str) -> None:
    python_path = _overlay_python(env_root)
    requirements = [f"{name}=={compat_version}.*" for name in _PUBLISHED_COMPAT_PACKAGES]
    if shutil.which("uv"):
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python_path),
                "--upgrade",
                "--reinstall",
                "--no-deps",
                *requirements,
            ],
            check=True,
            cwd=str(get_repo_root()),
        )
        return

    subprocess.run(
        [str(python_path), "-m", "pip", "install", "--upgrade", "--force-reinstall", "--no-deps", *requirements],
        check=True,
        cwd=str(get_repo_root()),
    )


def _validate_overlay_versions(installed_versions: dict[str, str | None], compat_version: str) -> tuple[str, str]:
    cogames_version = installed_versions.get("cogames")
    mettagrid_version = installed_versions.get("mettagrid")
    if cogames_version is None or mettagrid_version is None:
        raise ValueError(
            f"Compat overlay for {compat_version} did not install both cogames and mettagrid published packages."
        )

    cogames_compat = parse_compat_version(cogames_version)
    mettagrid_compat = parse_compat_version(mettagrid_version)
    if cogames_compat != compat_version:
        raise ValueError(
            f"Installed cogames {cogames_version} has compat {cogames_compat}, not requested compat {compat_version}."
        )
    if mettagrid_compat != compat_version:
        raise ValueError(
            f"Installed mettagrid {mettagrid_version} has compat {mettagrid_compat}, "
            f"not requested compat {compat_version}."
        )
    return cogames_version, mettagrid_version


def prepare_published_compat_overlay(repo_root: Path | str, compat_version: str) -> CompatPackageOverlay:
    compat_version = _normalize_compat_version(compat_version)
    env_root = _overlay_env_root(repo_root, compat_version)
    _ensure_overlay_env(env_root)
    _install_published_compat_packages(env_root, compat_version)
    installed_versions = _installed_overlay_versions(env_root)
    cogames_version, mettagrid_version = _validate_overlay_versions(installed_versions, compat_version)
    site_packages = _overlay_site_packages(env_root)
    return CompatPackageOverlay(
        compat_version=compat_version,
        env_root=env_root,
        site_packages=site_packages,
        cogames_version=cogames_version,
        mettagrid_version=mettagrid_version,
    )


def _filtered_pythonpath_entries(existing_pythonpath: str | None, repo_root: Path | str) -> list[str]:
    if not existing_pythonpath:
        return []

    repo_root = Path(repo_root).resolve()
    local_package_paths = {(repo_root / local_path).resolve() for local_path in _LOCAL_PACKAGE_PATHS}
    kept: list[str] = []
    for entry in existing_pythonpath.split(os.pathsep):
        if not entry:
            continue
        try:
            resolved = Path(entry).resolve()
        except OSError:
            kept.append(entry)
            continue
        if resolved in local_package_paths:
            continue
        kept.append(entry)
    return kept


def _repo_workspace_members(repo_root: Path | str) -> list[Path]:
    repo_root = Path(repo_root)
    pyproject_path = repo_root / "pyproject.toml"
    with pyproject_path.open("rb") as handle:
        pyproject = tomllib.load(handle)

    members = pyproject.get("tool", {}).get("uv", {}).get("workspace", {}).get("members", [])
    return [repo_root / member for member in members]


def _repo_source_roots(repo_root: Path | str) -> list[str]:
    repo_root = Path(repo_root).resolve()
    local_package_paths = {(repo_root / local_path).resolve() for local_path in _LOCAL_PACKAGE_PATHS}

    entries: list[str] = [str(repo_root)]
    for member in _repo_workspace_members(repo_root):
        for candidate_relpath in _WORKSPACE_SOURCE_DIR_CANDIDATES:
            candidate = (member / candidate_relpath).resolve()
            if not candidate.exists() or candidate in local_package_paths:
                continue
            entries.append(str(candidate))
    return _dedupe_existing_paths(entries)


def _ambient_site_packages() -> list[str]:
    entries = [
        sysconfig.get_path("purelib"),
        sysconfig.get_path("platlib"),
    ]
    return _dedupe_existing_paths(entries)


def _dedupe_existing_paths(entries: Sequence[str | None]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()

    for entry in entries:
        if not entry:
            continue
        resolved = str(Path(entry).resolve())
        if resolved in seen or not Path(resolved).exists():
            continue
        seen.add(resolved)
        deduped.append(resolved)

    return deduped


def _compat_pythonpath(site_packages: Path, existing_pythonpath: str | None, repo_root: Path | str) -> str:
    entries = [
        str(site_packages),
        *_repo_source_roots(repo_root),
        *_ambient_site_packages(),
        *_filtered_pythonpath_entries(existing_pythonpath, repo_root),
    ]
    return os.pathsep.join(_dedupe_existing_paths(entries))


def run_in_compat_version(compat_version: str, argv: list[str], script_path: str) -> int:
    if os.getenv("METTA_COMPAT_VERSION_ACTIVE") == "1":
        return -1

    repo_root = get_repo_root()
    overlay = prepare_published_compat_overlay(repo_root, compat_version)
    env = os.environ.copy()
    env["METTA_COMPAT_VERSION_ACTIVE"] = "1"
    env["METTA_COMPAT_VERSION"] = overlay.compat_version
    env["METTA_COMPAT_COGAMES_VERSION"] = overlay.cogames_version
    env["METTA_COMPAT_METTAGRID_VERSION"] = overlay.mettagrid_version
    env["METTA_COMPAT_ENV_ROOT"] = str(overlay.env_root)
    env["METTA_COMPAT_SITE_PACKAGES"] = str(overlay.site_packages)
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONPATH"] = _compat_pythonpath(overlay.site_packages, env.get("PYTHONPATH"), repo_root)
    command = [str(_overlay_python(overlay.env_root)), script_path, *argv]
    return subprocess.run(command, cwd=str(repo_root), env=env).returncode
