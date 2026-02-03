import shutil
from pathlib import Path

from metta.setup.components.base import SetupModule
from metta.setup.registry import register_module
from metta.setup.utils import info, success, warning
from softmax.aws.secrets_manager import get_secretsmanager_secret

CACHE_DIR = Path.home() / ".metta"
CACHE_FILE = CACHE_DIR / "dd_api_key"


@register_module
class SkillsLeaderboardSetup(SetupModule):
    install_once = True

    @property
    def name(self) -> str:
        return "skills-leaderboard"

    @property
    def description(self) -> str:
        return "Datadog API key for skills usage tracking"

    def dependencies(self) -> list[str]:
        return ["aws"]

    def check_installed(self) -> bool:
        if not CACHE_FILE.exists():
            return False
        if not CACHE_FILE.read_text().strip():
            return False
        if not shutil.which("jq"):
            return False
        return True

    def install(self, non_interactive: bool = False, force: bool = False) -> None:
        if not shutil.which("jq"):
            warning("jq is not installed. Install it with `metta install system`")
            return

        api_key = get_secretsmanager_secret("datadog/api-key", require_exists=False)
        if not api_key:
            warning("Could not fetch Datadog API key from AWS Secrets Manager.")
            return

        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        CACHE_FILE.write_text(api_key)
        CACHE_FILE.chmod(0o600)
        info(f"DD API key cached at {CACHE_FILE}")

        info("When you start claude code sessions from the repo's root, your skill usage will now be tracked")
        success("https://app.datadoghq.com/dashboard/ebw-5wr-q8h")
