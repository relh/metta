#!/usr/bin/env python3
import os
import textwrap

import pytest

from metta.setup.profiles import UserType
from tests.setup.test_base import BaseMettaSetupTest


class AWSAssertionsMixin:
    """Helpers for asserting AWS-related filesystem state in tests."""

    def _check_aws_config_exists(self) -> bool:  # type: ignore[override]
        aws_dir = self.test_home / ".aws"  # type: ignore[attr-defined]
        if not aws_dir.exists():
            return False
        config_file = aws_dir / "config"
        return config_file.exists()

    def _check_aws_profile_config(self, profile_name: str) -> bool:  # type: ignore[override]
        config_file = self.test_home / ".aws" / "config"  # type: ignore[attr-defined]
        if not config_file.exists():
            return False
        content = config_file.read_text()
        return f"[profile {profile_name}]" in content

    def _check_aws_sso_session_config(self, session_name: str) -> bool:  # type: ignore[override]
        """Check if SSO session configuration exists in AWS config."""
        config_file = self.test_home / ".aws" / "config"  # type: ignore[attr-defined]
        if not config_file.exists():
            return False
        content = config_file.read_text()
        return f"[sso-session {session_name}]" in content

    def _read_aws_config(self) -> str:  # type: ignore[override]
        config_file = self.test_home / ".aws" / "config"  # type: ignore[attr-defined]
        return config_file.read_text() if config_file.exists() else ""

    def _check_sso_session_has_required_fields(self, session_name: str) -> tuple[bool, str]:  # type: ignore[override]
        """Check if SSO session has all required fields."""
        config_file = self.test_home / ".aws" / "config"  # type: ignore[attr-defined]
        if not config_file.exists():
            return False, "Config file does not exist"

        content = config_file.read_text()

        if f"[sso-session {session_name}]" not in content:
            return False, f"SSO session [{session_name}] not found"

        required_fields = [
            "sso_start_url = https://softmaxx.awsapps.com/start/",
            "sso_region = us-east-1",
            "sso_registration_scopes = sso:account:access",
        ]

        missing_fields = []
        for field in required_fields:
            if field not in content:
                missing_fields.append(field)

        if missing_fields:
            return False, f"Missing fields: {missing_fields}"

        return True, "All required fields present"


@pytest.mark.setup
@pytest.mark.profile("softmax")
class TestAWSProfileSoftmax(AWSAssertionsMixin, BaseMettaSetupTest):
    """Tests for AWS profile setup functionality."""

    def test_softmax_profile_aws_installation(self):
        """Test that softmax profile AWS installation works correctly."""
        print(f"DEBUG: HOME={os.environ.get('HOME')}")
        print(f"DEBUG: ZDOTDIR={os.environ.get('ZDOTDIR')}")
        print(f"DEBUG: Test home={self.test_home}")

        self._create_test_config(UserType.SOFTMAX)

        # Run AWS install (bypass base class mocking)

        result = self._run_metta_command(["install", "aws", "--force"])
        assert result.returncode == 0, f"AWS install failed: {result.stderr}"

        # Check that AWS_PROFILE export was added to shell config
        zshrc_path = self._get_zshrc_path()
        bashrc_path = self._get_bashrc_path()

        # Debug what's actually in the zshrc file
        zshrc_content = zshrc_path.read_text() if zshrc_path.exists() else "FILE NOT EXISTS"
        print(f"DEBUG: zshrc_path={zshrc_path}")
        print(f"DEBUG: zshrc content: {repr(zshrc_content)}")

        assert self._check_shell_config_contains(zshrc_path, "export AWS_PROFILE=softmax"), (
            f"AWS_PROFILE export should be added to {zshrc_path} for softmax profile. Content: {repr(zshrc_content)}"
        )

        # Also check .bashrc
        assert self._check_shell_config_contains(bashrc_path, "export AWS_PROFILE=softmax"), (
            f"AWS_PROFILE export should be added to {bashrc_path} for softmax profile"
        )

        # Check that AWS config exists
        assert self._check_aws_config_exists(), "AWS config should be created"

        # Check that specific profiles are configured
        assert self._check_aws_profile_config("softmax"), "softmax profile should be configured"
        assert self._check_aws_profile_config("softmax-admin"), "softmax-admin profile should be configured"
        assert self._check_aws_profile_config("softmax-org"), "softmax-org profile should be configured"
        assert self._check_aws_profile_config("polis-admin"), "polis-admin profile should be configured"

        # Check the exact format of the export
        zshrc_content = zshrc_path.read_text()
        assert "export AWS_PROFILE=softmax" in zshrc_content, (
            "AWS_PROFILE export should be exactly 'export AWS_PROFILE=softmax'"
        )

        # Check that it's on its own line
        lines = zshrc_content.split("\n")
        assert "export AWS_PROFILE=softmax" in lines, "AWS_PROFILE export should be on its own line"

        # Check that the setup script was mentioned in output
        assert "Running AWS profile setup" in result.stdout, (
            "Should mention running AWS profile setup for softmax profile"
        )

        # CRITICAL: Check that SSO session configuration exists (this would have caught the bug!)
        assert self._check_aws_sso_session_config("softmax-sso"), (
            "SSO session 'softmax-sso' should be configured in AWS config"
        )

        # Check that SSO session has all required fields
        has_fields, message = self._check_sso_session_has_required_fields("softmax-sso")
        assert has_fields, f"SSO session missing required configuration: {message}"

        # Verify profiles reference the SSO session correctly
        config_content = self._read_aws_config()
        assert "sso_session = softmax-sso" in config_content, "Profiles should reference 'sso_session = softmax-sso'"
        assert "# BEGIN softmax-managed" in config_content, "Managed AWS config block should be marked"
        assert "# END softmax-managed" in config_content, "Managed AWS config block should be marked"

    def test_softmax_profile_aws_installation_is_idempotent(self):
        """Repeated installs should replace the managed block instead of duplicating it."""
        self._create_test_config(UserType.SOFTMAX)

        first_result = self._run_metta_command(["install", "aws", "--force"])
        assert first_result.returncode == 0, f"Initial AWS install failed: {first_result.stderr}"

        second_result = self._run_metta_command(["install", "aws", "--force"])
        assert second_result.returncode == 0, f"Second AWS install failed: {second_result.stderr}"

        config_content = self._read_aws_config()
        assert config_content.count("# BEGIN softmax-managed") == 1, "Managed block should only be written once"
        assert config_content.count("# END softmax-managed") == 1, "Managed block should only be written once"
        assert config_content.count("[profile softmax]") == 1, "Managed profiles should not be duplicated"
        assert config_content.count("[profile softmax-org]") == 1, "Explicit managed profiles should not duplicate"

    def test_softmax_force_install_preserves_unmanaged_aws_state(self):
        """Force install should replace only managed config and preserve unrelated AWS files."""
        aws_dir = self.test_home / ".aws"
        aws_dir.mkdir(parents=True, exist_ok=True)

        config_path = aws_dir / "config"
        config_path.write_text(
            textwrap.dedent(
                """
                [profile personal]
                region = us-west-2

                [sso-session softmax-sso]
                sso_start_url = https://softmaxx.awsapps.com/start/
                sso_region = us-east-1
                sso_registration_scopes = sso:account:access

                [profile softmax]
                sso_session = softmax-sso
                sso_account_id = 751442549699
                sso_role_name = OldRole
                region = us-east-1
                """
            ).strip()
            + "\n"
        )

        credentials_path = aws_dir / "credentials"
        credentials_content = "[personal]\naws_access_key_id = test\naws_secret_access_key = secret\n"
        credentials_path.write_text(credentials_content)

        self._create_test_config(UserType.SOFTMAX)

        result = self._run_metta_command(["install", "aws", "--force"])
        assert result.returncode == 0, f"AWS force install failed: {result.stderr}"

        config_content = self._read_aws_config()
        assert "[profile personal]" in config_content, "Unmanaged profiles should be preserved"
        assert "OldRole" not in config_content, "Legacy managed profile entries should be replaced"
        assert config_content.count("[profile softmax]") == 1, "Managed profiles should be rewritten in place"
        assert config_content.count("# BEGIN softmax-managed") == 1, "Managed block marker should not duplicate"
        assert config_content.count("# END softmax-managed") == 1, "Managed block marker should not duplicate"
        assert credentials_path.read_text() == credentials_content, "Reset should not delete unrelated AWS files"

    def test_softmax_profile_aws_installation_with_zdotdir(self):
        """Test that softmax profile AWS installation works with ZDOTDIR set."""
        # Set up ZDOTDIR
        zdotdir = self.test_home / "config" / "zsh"
        zdotdir.mkdir(parents=True, exist_ok=True)
        self._set_env_var("ZDOTDIR", str(zdotdir))

        # Create shell config files in ZDOTDIR (zsh) and HOME (bash)
        zshrc = zdotdir / ".zshrc"
        bashrc = self.test_home / ".bashrc"
        zshrc.write_text("# Test zshrc in ZDOTDIR\n")
        bashrc.write_text("# Test bashrc in $HOME\n")

        self._create_test_config(UserType.SOFTMAX)

        # Run AWS install (bypass base class mocking)
        result = self._run_metta_command(["install", "aws", "--force"])
        assert result.returncode == 0, f"AWS install failed: {result.stderr}"

        # Check that AWS_PROFILE export was added to shell config in ZDOTDIR
        zshrc_path = self._get_zshrc_path()
        bashrc_path = self._get_bashrc_path()

        assert self._check_shell_config_contains(zshrc_path, "export AWS_PROFILE=softmax"), (
            f"AWS_PROFILE export should be added to {zshrc_path} for softmax profile with ZDOTDIR"
        )

        # Also check .bashrc in HOME (not ZDOTDIR)
        assert self._check_shell_config_contains(bashrc_path, "export AWS_PROFILE=softmax"), (
            f"AWS_PROFILE export should be added to {bashrc_path} for softmax profile with ZDOTDIR"
        )

        # Check that existing content is preserved and export is added
        zshrc_content = zshrc_path.read_text()
        print(zshrc_content)
        assert "export AWS_PROFILE=softmax" in zshrc_content, "AWS_PROFILE export should be added to .zshrc"

        bashrc_content = bashrc_path.read_text()
        print(bashrc_content)
        assert "export AWS_PROFILE=softmax" in bashrc_content, "AWS_PROFILE export should be added to .bashrc"

        export_count = zshrc_content.count("export AWS_PROFILE=softmax")
        print(export_count)
        assert export_count == 1, f"Should have exactly one AWS_PROFILE export, found {export_count}"


@pytest.mark.setup
@pytest.mark.profile("external")
class TestAWSProfileExternal(AWSAssertionsMixin, BaseMettaSetupTest):
    """Ensure the external profile does not touch AWS config or shell exports."""

    def test_external_install_writes_no_aws_state(self):
        """Install with external profile and assert no AWS artifacts were written."""
        # Create external profile config
        self._create_test_config(UserType.EXTERNAL)

        # Run install (bypass base class mocking)
        result = self._run_metta_command(["install", "aws"])
        assert result.returncode == 0, f"Install failed: {result.stderr}"

        # Assert no AWS config directory/file was created
        assert not self._check_aws_config_exists(), "External profile should not create ~/.aws/config"

        # Assert no AWS profiles are present
        assert not self._check_aws_profile_config("softmax"), "External profile should not add softmax profile"
        assert not self._check_aws_profile_config("softmax-admin"), (
            "External profile should not add softmax-admin profile"
        )

        # Assert no AWS_PROFILE export added to shell configs
        zshrc_path = self._get_zshrc_path()
        bashrc_path = self._get_bashrc_path()
        assert not self._check_shell_config_contains(zshrc_path, "export AWS_PROFILE=softmax"), (
            f"External profile should not add AWS_PROFILE to {zshrc_path}"
        )
        assert not self._check_shell_config_contains(bashrc_path, "export AWS_PROFILE=softmax"), (
            f"External profile should not add AWS_PROFILE to {bashrc_path}"
        )
