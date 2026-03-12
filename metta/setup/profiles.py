from enum import Enum

from typing_extensions import NotRequired, TypedDict

from metta.common.util.constants import METTA_AWS_ACCOUNT_ID, METTA_AWS_REGION, METTA_SKYPILOT_URL, METTA_WANDB_ENTITY


class UserType(Enum):
    SOFTMAX = "softmax"
    SOFTMAX_DOCKER = "softmax-docker"
    SOFTMAX_CONTRACTOR = "softmax-contractor"
    EXTERNAL = "external"
    CLOUD = "cloud"
    CUSTOM = "custom"

    @property
    def is_softmax(self) -> bool:
        return self in (UserType.SOFTMAX, UserType.SOFTMAX_DOCKER)

    def get_description(self) -> str:
        descriptions = {
            UserType.EXTERNAL: "External contributor",
            UserType.CLOUD: "User with own cloud account",
            UserType.SOFTMAX: "Softmax employee",
            UserType.SOFTMAX_DOCKER: "Softmax (Docker)",
            UserType.SOFTMAX_CONTRACTOR: "Softmax contractor",
            UserType.CUSTOM: "Custom configuration",
        }
        return descriptions.get(self, self.value)


class ComponentConfig(TypedDict):
    enabled: bool
    expected_connection: NotRequired[str | None]


class ProfileConfig(TypedDict):
    components: dict[str, ComponentConfig]


PROFILE_DEFINITIONS: dict[UserType, ProfileConfig] = {
    UserType.EXTERNAL: {
        "components": {
            "bootstrap": {"enabled": True},
            "system": {"enabled": True},
            "uv": {"enabled": True},
            "cogents": {"enabled": False},
            "js-toolchain": {"enabled": True},
            "githooks": {"enabled": True},
            "observatory-key": {"enabled": False},
            "aws": {"enabled": False},
            "bedrock": {"enabled": False},
            "wandb": {"enabled": False},
            "skypilot": {"enabled": False},
            "tailscale": {"enabled": False},
            "scratchpad": {"enabled": True},
            "pr-similarity": {"enabled": False},
        }
    },
    UserType.CLOUD: {
        "components": {
            "bootstrap": {"enabled": True},
            "system": {"enabled": True},
            "uv": {"enabled": True},
            "cogents": {"enabled": False},
            "js-toolchain": {"enabled": True},
            "githooks": {"enabled": True},
            "observatory-key": {"enabled": False},
            "aws": {"enabled": True},
            "bedrock": {"enabled": False},
            "wandb": {"enabled": True},
            "skypilot": {"enabled": True},
            "tailscale": {"enabled": False},
            "scratchpad": {"enabled": True},
            "pr-similarity": {"enabled": False},
        }
    },
    UserType.SOFTMAX_DOCKER: {
        "components": {
            "bootstrap": {"enabled": True},
            "system": {"enabled": True},
            "uv": {"enabled": True},
            "cogents": {"enabled": False},
            "js-toolchain": {"enabled": False},
            "githooks": {"enabled": False},
            "observatory-key": {"enabled": False},
            "aws": {"enabled": True, "expected_connection": METTA_AWS_ACCOUNT_ID},
            "bedrock": {"enabled": False},
            "wandb": {"enabled": True, "expected_connection": METTA_WANDB_ENTITY},
            "skypilot": {"enabled": False},
            "tailscale": {"enabled": False},
            "scratchpad": {"enabled": False},
            "pr-similarity": {"enabled": False},
            "binary-symlinks": {"enabled": True},
        }
    },
    UserType.SOFTMAX_CONTRACTOR: {
        "components": {
            "bootstrap": {"enabled": True},
            "system": {"enabled": True},
            "uv": {"enabled": True},
            "cogents": {"enabled": False},
            "js-toolchain": {"enabled": True},
            "githooks": {"enabled": True},
            "observatory-key": {"enabled": False},
            "aws": {"enabled": True},
            "bedrock": {"enabled": True, "expected_connection": METTA_AWS_REGION},
            "wandb": {"enabled": True},
            "skypilot": {"enabled": False},
            "tailscale": {"enabled": False},
            "scratchpad": {"enabled": True},
            "pr-similarity": {"enabled": False},
        }
    },
    UserType.SOFTMAX: {
        "components": {
            "bootstrap": {"enabled": True},
            "system": {"enabled": True},
            "uv": {"enabled": True},
            "cogents": {"enabled": True},
            "codeclip": {"enabled": True},
            "apps": {"enabled": True},
            "js-toolchain": {"enabled": True},
            "githooks": {"enabled": True},
            "observatory-key": {"enabled": True, "expected_connection": "@stem.ai"},
            "aws": {"enabled": True, "expected_connection": METTA_AWS_ACCOUNT_ID},
            "bedrock": {"enabled": True, "expected_connection": METTA_AWS_REGION},
            "smart-plugs": {"enabled": True},
            "wandb": {"enabled": True, "expected_connection": METTA_WANDB_ENTITY},
            "skypilot": {"enabled": True, "expected_connection": METTA_SKYPILOT_URL},
            "tailscale": {"enabled": False, "expected_connection": "@stem.ai"},
            "scratchpad": {"enabled": True},
            "helm": {"enabled": True},
            "docker-compose": {"enabled": True},
            "pr-similarity": {"enabled": False},
            "ide-extensions": {"enabled": True},
            "binary-symlinks": {"enabled": True},
        }
    },
}
