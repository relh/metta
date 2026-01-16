from __future__ import annotations

import json
from pathlib import Path

from metta.setup.components.base import SetupModule
from metta.setup.registry import register_module
from metta.setup.saved_settings import get_saved_settings
from metta.setup.utils import info, success, warning
from softmax.aws.secrets_manager import get_secretsmanager_secret

DEFAULT_SECRET_NAME = "smart-plugs/founders-wing"
DEFAULT_CONFIG_PATH = "~/.config/metta/smart_plugs.json"


@register_module
class SmartPlugsSetup(SetupModule):
    install_once = True

    @property
    def name(self) -> str:  # type: ignore[override]
        return "smart-plugs"

    @property
    def description(self) -> str:
        return "Fetch smart plug configuration from Secrets Manager"

    def dependencies(self) -> list[str]:
        return ["aws"]

    def get_configuration_options(self) -> dict[str, tuple[object, str]]:
        return {
            "secret_name": (DEFAULT_SECRET_NAME, "Secrets Manager name containing smart plug config JSON"),
        }

    def check_installed(self) -> bool:
        config_path = Path(DEFAULT_CONFIG_PATH).expanduser()
        if not config_path.exists():
            return False
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            return False
        return isinstance(payload, dict) and "plugs" in payload

    def install(self, non_interactive: bool = False, force: bool = False) -> None:
        saved_settings = get_saved_settings()
        if not saved_settings.user_type.is_softmax:
            warning("Smart plug setup is only available for Softmax users. Skipping.")
            return

        secret_name = self.get_setting("secret_name", DEFAULT_SECRET_NAME)
        config_path = Path(DEFAULT_CONFIG_PATH).expanduser()

        info(f"Fetching smart plug config from Secrets Manager ({secret_name})...")
        secret = get_secretsmanager_secret(secret_name, require_exists=False)
        if not secret:
            warning("Smart plug secret not found. Populate Secrets Manager and rerun 'metta install smart-plugs'.")
            return

        try:
            payload = json.loads(secret)
        except Exception as exc:
            warning(f"Smart plug secret is not valid JSON config: {exc}")
            return
        if not isinstance(payload, dict) or "plugs" not in payload:
            warning("Smart plug secret must be a JSON object with a 'plugs' list")
            return

        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        try:
            config_path.chmod(0o600)
        except Exception:
            warning(f"Could not set permissions on {config_path}")

        success(f"Smart plug config written to {config_path}")
        info("Observatory backend reads smart plug config from the default path.")
