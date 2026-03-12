from typing import TypedDict

from metta.common.util.constants import SOFTMAX_S3_POLICY_PREFIX, SOFTMAX_S3_REPLAYS_PREFIX
from metta.setup.components.base import SetupModule
from metta.setup.profiles import UserType
from metta.setup.registry import register_module
from metta.setup.saved_settings import get_saved_settings
from metta.setup.utils import info


class AwsConfigSettings(TypedDict):
    replay_dir: str
    policy_remote_prefix: str | None


@register_module
class AWSSetup(SetupModule):
    install_once = True

    @property
    def description(self) -> str:
        return "AWS configuration and credentials"

    def check_installed(self) -> bool:
        try:
            import boto3  # noqa: F401, PLC0415

            return True
        except ImportError:
            return False

    def install(self, non_interactive: bool = False, force: bool = False) -> None:
        """Set up AWS CLI configuration and credentials.

        For softmax-docker profile, skips setup as AWS access should be provided
        via IAM roles or environment variables. For other profiles, provides
        guidance on configuring AWS CLI.

        Args:
            non_interactive: If True, skip interactive configuration prompts
        """
        saved_settings = get_saved_settings()
        if saved_settings.user_type == UserType.SOFTMAX_DOCKER:
            info("""
            AWS access for this profile should be provided via IAM roles or environment variables.
            Skipping setup.
            """)
            return
        if saved_settings.user_type in (UserType.SOFTMAX, UserType.SOFTMAX_CONTRACTOR):
            info("""
                Your AWS access should have been provisioned.
                If you don't have access, contact your team lead.

                Running AWS profile setup...
            """)
            env = {}
            if saved_settings.user_type == UserType.SOFTMAX_CONTRACTOR:
                env["AWS_PROFILE_DEFAULT"] = "contractor-softmax"
            self.run_script("devops/aws/setup_aws_profiles.sh", args=["--reset"] if force else [], env=env or None)
        else:
            info("Configure your AWS credentials using `aws configure`")

    def check_connected_as(self) -> str | None:
        try:
            # Keep local import: optional dependency
            import boto3  # noqa: PLC0415

            sts = boto3.client("sts")
            return sts.get_caller_identity()["Account"]
        except Exception:
            return None

    @property
    def can_remediate_connected_status_with_install(self) -> bool:
        return True

    def to_config_settings(self) -> AwsConfigSettings:
        saved_settings = get_saved_settings()
        if saved_settings.user_type.is_softmax or saved_settings.user_type == UserType.SOFTMAX_CONTRACTOR:
            return AwsConfigSettings(
                replay_dir=SOFTMAX_S3_REPLAYS_PREFIX,
                policy_remote_prefix=SOFTMAX_S3_POLICY_PREFIX,
            )
        return AwsConfigSettings(replay_dir="./train_dir/replays/", policy_remote_prefix=None)
