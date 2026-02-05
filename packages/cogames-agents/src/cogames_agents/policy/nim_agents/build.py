from __future__ import annotations

import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

NIM_AGENTS_DIR = Path(__file__).resolve().parent
NIMBY_LOCK = NIM_AGENTS_DIR / "nimby.lock"
BINDINGS_DIR = NIM_AGENTS_DIR / "bindings" / "generated"


def _find_version_file(name: str) -> str:
    candidate = NIM_AGENTS_DIR / name
    if candidate.exists():
        return candidate.read_text().strip()
    for parent in NIM_AGENTS_DIR.parents:
        candidate = parent / name
        if candidate.exists():
            return candidate.read_text().strip()
        if parent == parent.parent:
            break
    raise FileNotFoundError(f"{name} not found in any ancestor of {NIM_AGENTS_DIR}")


NIM_VERSION = _find_version_file(".nim-version")
NIMBY_VERSION = _find_version_file(".nimby-version")


def _get_nimby_url() -> str | None:
    system = platform.system()
    arch = platform.machine()
    if system == "Linux" and arch == "x86_64":
        return f"https://github.com/treeform/nimby/releases/download/{NIMBY_VERSION}/nimby-Linux-X64"
    elif system == "Linux" and arch == "aarch64":
        return f"https://github.com/treeform/nimby/releases/download/{NIMBY_VERSION}/nimby-Linux-ARM64"
    elif system == "Darwin" and arch == "arm64":
        return f"https://github.com/treeform/nimby/releases/download/{NIMBY_VERSION}/nimby-macOS-ARM64"
    elif system == "Darwin" and arch == "x86_64":
        return f"https://github.com/treeform/nimby/releases/download/{NIMBY_VERSION}/nimby-macOS-X64"
    return None


def _nim_already_installed() -> bool:
    nim = shutil.which("nim")
    if nim is None:
        return False
    result = subprocess.run([nim, "--version"], capture_output=True, text=True)
    return f"Nim Compiler Version {NIM_VERSION}" in result.stdout


def _install_nim() -> None:
    if _nim_already_installed():
        return

    nimby_url = _get_nimby_url()
    if nimby_url is None:
        system = platform.system()
        arch = platform.machine()
        raise RuntimeError(
            f"Nim {NIM_VERSION} is not installed and nimby download is not available for {system} {arch}. "
            "Please install Nim manually (https://nim-lang.org/install.html) or build nimby from source."
        )

    nim_bin_dir = Path.home() / ".nimby" / "nim" / "bin"
    dst = nim_bin_dir / "nimby"
    with tempfile.TemporaryDirectory() as tmp:
        nimby = Path(tmp) / "nimby"
        urllib.request.urlretrieve(nimby_url, nimby)
        nimby.chmod(nimby.stat().st_mode | stat.S_IEXEC)
        subprocess.check_call([str(nimby), "use", NIM_VERSION])
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(nimby, dst)

    os.environ["PATH"] = f"{dst.parent}{os.pathsep}" + os.environ.get("PATH", "")
    os.environ["PATH"] = f"{nim_bin_dir}{os.pathsep}" + os.environ.get("PATH", "")


def build_nim() -> None:
    _install_nim()

    if shutil.which("nimby") is not None:
        subprocess.check_call(["nimby", "sync", "-g", str(NIMBY_LOCK)], cwd=NIM_AGENTS_DIR)

    BINDINGS_DIR.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(["nim", "c", "nim_agents.nim"], cwd=NIM_AGENTS_DIR, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        print(result.stdout, file=sys.stderr)
        raise RuntimeError(f"Failed to build Nim agents: {result.returncode}")
