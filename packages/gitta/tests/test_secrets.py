import os
from unittest.mock import patch

import pytest

from gitta.secrets import get_github_token


@pytest.fixture(autouse=True)
def clean_env():
    """Clean environment variables before each test."""
    original = os.environ.get("GITHUB_TOKEN")
    if "GITHUB_TOKEN" in os.environ:
        del os.environ["GITHUB_TOKEN"]
    yield
    if original is not None:
        os.environ["GITHUB_TOKEN"] = original
    elif "GITHUB_TOKEN" in os.environ:
        del os.environ["GITHUB_TOKEN"]


class TestGetGithubToken:
    def test_from_env_var(self):
        os.environ["GITHUB_TOKEN"] = "ghp_test123"
        assert get_github_token() == "ghp_test123"

    def test_from_gh_cli(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = "ghp_from_cli\n"
            mock_run.return_value.returncode = 0
            token = get_github_token()
            assert token == "ghp_from_cli"
            mock_run.assert_called_once()

    def test_env_var_takes_precedence_over_gh_cli(self):
        os.environ["GITHUB_TOKEN"] = "ghp_from_env"
        with patch("subprocess.run") as mock_run:
            token = get_github_token()
            assert token == "ghp_from_env"
            mock_run.assert_not_called()

    def test_returns_none_when_gh_cli_fails(self):
        with patch("subprocess.run") as mock_run:
            import subprocess

            mock_run.side_effect = subprocess.CalledProcessError(1, "gh")
            assert get_github_token() is None

    def test_returns_none_when_gh_not_installed(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()
            assert get_github_token() is None

    def test_returns_none_when_gh_returns_empty(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.stdout = "   \n"
            mock_run.return_value.returncode = 0
            assert get_github_token() is None
