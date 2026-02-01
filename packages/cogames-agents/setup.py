#!/usr/bin/env python3
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

from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.command.develop import develop
from setuptools.command.install import install
from setuptools.dist import Distribution

NIM_AGENTS_DIR = Path(__file__).parent / "src" / "cogames_agents" / "policy" / "nim_agents"
NIMBY_LOCK = NIM_AGENTS_DIR / "nimby.lock"
BINDINGS_DIR = NIM_AGENTS_DIR / "bindings" / "generated"

_PKG_ROOT = Path(__file__).resolve().parent


def _read_dotfile_version(path: Path) -> str:
    return path.read_text().strip()


NIM_VERSION = _read_dotfile_version(_PKG_ROOT / ".nim-version")
NIMBY_VERSION = _read_dotfile_version(_PKG_ROOT / ".nimby-version")


def _get_nimby_url() -> str | None:
    """Get the nimby download URL for the current platform, or None if not supported."""
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
    else:
        return None


def _build_nim() -> None:
    system = platform.system()
    arch = platform.machine()

    nimby_url = _get_nimby_url()
    nim_bin_dir = Path.home() / ".nimby" / "nim" / "bin"

    if nimby_url is not None:
        # Download and install nimby
        dst = nim_bin_dir / "nimby"
        with tempfile.TemporaryDirectory() as tmp:
            nimby = Path(tmp) / "nimby"
            urllib.request.urlretrieve(nimby_url, nimby)
            nimby.chmod(nimby.stat().st_mode | stat.S_IEXEC)
            subprocess.check_call([str(nimby), "use", NIM_VERSION])

            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(nimby, dst)

        os.environ["PATH"] = f"{dst.parent}{os.pathsep}" + os.environ.get("PATH", "")
    else:
        # For unsupported platforms, assume nim/nimby are pre-installed
        if shutil.which("nim") is None:
            raise RuntimeError(
                f"Nim is not installed and nimby download is not available for {system} {arch}. "
                "Please install Nim manually (https://nim-lang.org/install.html) or build nimby from source."
            )

    # Ensure nim/nimble binaries installed by nimby are discoverable by subprocesses.
    os.environ["PATH"] = f"{nim_bin_dir}{os.pathsep}" + os.environ.get("PATH", "")

    # Sync Nim dependencies using nimby
    if shutil.which("nimby") is not None:
        subprocess.check_call(["nimby", "sync", "-g", str(NIMBY_LOCK)], cwd=NIM_AGENTS_DIR)

    # Create output directory for compiled binaries
    BINDINGS_DIR.mkdir(parents=True, exist_ok=True)

    # Compile Nim agents
    result = subprocess.run(["nim", "c", "nim_agents.nim"], cwd=NIM_AGENTS_DIR, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        print(result.stdout, file=sys.stderr)
        raise RuntimeError(f"Failed to build Nim agents: {result.returncode}")


class _EnsureNimMixin:
    def run(self, *args, **kwargs):  # type: ignore[override]
        _build_nim()
        super().run(*args, **kwargs)  # type: ignore[misc]


class BuildPyCommand(_EnsureNimMixin, build_py): ...


class DevelopCommand(_EnsureNimMixin, develop): ...


class InstallCommand(_EnsureNimMixin, install): ...


class BinaryDistribution(Distribution):
    def has_ext_modules(self) -> bool:
        return True


setup(
    cmdclass={
        "build_py": BuildPyCommand,
        "develop": DevelopCommand,
        "install": InstallCommand,
    },
    distclass=BinaryDistribution,
)
