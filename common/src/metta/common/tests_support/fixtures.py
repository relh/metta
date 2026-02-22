"""Shared test fixtures for metta tests."""

from typing import Literal

import pytest

_ScopeName = Literal["session", "package", "module", "class", "function"]


def docker_client_fixture(scope: _ScopeName = "class"):
    """Factory function that creates the docker_client fixture."""

    @pytest.fixture(scope=scope)
    def docker_client():
        try:
            # Keep local optional import
            import docker  # noqa: PLC0415
            from docker.errors import DockerException  # noqa: PLC0415
        except ImportError:
            pytest.skip("Docker is not installed")

        try:
            client = docker.from_env(timeout=5)
            client.ping()
            return client
        except (DockerException, ConnectionError, TimeoutError) as e:
            pytest.skip(f"Docker daemon not available: {e}")

    return docker_client
