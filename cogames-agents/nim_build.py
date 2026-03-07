from __future__ import annotations

# Custom build backend (PEP 517/660) that ensures Nim bindings are generated for
# editable installs and wheels, similar to mettagrid's bazel_build backend.
from nim_build_support import build_nim_agents
from setuptools.build_meta import (
    build_editable as _build_editable,
)
from setuptools.build_meta import (
    build_sdist as _build_sdist,
)
from setuptools.build_meta import (
    build_wheel as _build_wheel,
)
from setuptools.build_meta import (
    get_requires_for_build_editable as _get_requires_for_build_editable,
)
from setuptools.build_meta import (
    get_requires_for_build_sdist as _get_requires_for_build_sdist,
)
from setuptools.build_meta import (
    get_requires_for_build_wheel as _get_requires_for_build_wheel,
)
from setuptools.build_meta import (
    prepare_metadata_for_build_editable as _prepare_metadata_for_build_editable,
)
from setuptools.build_meta import (
    prepare_metadata_for_build_wheel as _prepare_metadata_for_build_wheel,
)


def get_requires_for_build_wheel(config_settings=None):
    return _get_requires_for_build_wheel(config_settings)


def get_requires_for_build_editable(config_settings=None):
    return _get_requires_for_build_editable(config_settings)


def get_requires_for_build_sdist(config_settings=None):
    return _get_requires_for_build_sdist(config_settings)


def prepare_metadata_for_build_wheel(metadata_directory: str, config_settings=None) -> str:
    return _prepare_metadata_for_build_wheel(metadata_directory, config_settings=config_settings)


def prepare_metadata_for_build_editable(metadata_directory: str, config_settings=None) -> str:
    return _prepare_metadata_for_build_editable(metadata_directory, config_settings=config_settings)


def build_wheel(wheel_directory: str, config_settings=None, metadata_directory: str | None = None) -> str:
    build_nim_agents()
    return _build_wheel(wheel_directory, config_settings=config_settings, metadata_directory=metadata_directory)


def build_editable(wheel_directory: str, config_settings=None, metadata_directory: str | None = None) -> str:
    build_nim_agents()
    return _build_editable(wheel_directory, config_settings=config_settings, metadata_directory=metadata_directory)


def build_sdist(sdist_directory: str, config_settings=None) -> str:
    # sdist should include Nim sources; compilation happens when building/installing a wheel.
    return _build_sdist(sdist_directory, config_settings=config_settings)
