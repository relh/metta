#!/usr/bin/env python3
from __future__ import annotations

import runpy
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.command.develop import develop
from setuptools.command.install import install
from setuptools.dist import Distribution

_BUILD_MODULE = Path(__file__).parent / "src" / "cogames_agents" / "policy" / "nim_agents" / "build.py"


def _build_nim() -> None:
    mod = runpy.run_path(str(_BUILD_MODULE))
    mod["build_nim"]()


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
