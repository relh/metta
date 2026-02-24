from pathlib import Path

from metta.setup.components.base import SetupModule
from metta.setup.registry import register_module
from metta.setup.utils import info, success

COGENTS_REPO = "git@github.com:Metta-AI/cogents.git"

SYMLINKS: dict[str, str] = {
    ".claude/skills": "skills",
    ".codex/skills": "skills",
    ".cursor/skills": "skills",
    ".cursor/agents": "subagents",
}


@register_module
class CogentsSetup(SetupModule):
    always_required = True
    install_once = True

    @property
    def name(self) -> str:
        return "cogents"

    @property
    def description(self) -> str:
        return "Agent definitions repo (skills, subagents, prompts)"

    def _cogents_dir(self) -> Path:
        return self.repo_root.parent / "cogents"

    def check_installed(self) -> bool:
        cogents = self._cogents_dir()
        if not (cogents / ".git").is_dir():
            return False
        for link_rel in SYMLINKS:
            link = self.repo_root / link_rel
            if not link.is_symlink():
                return False
        return True

    def install(self, non_interactive: bool = False, force: bool = False) -> None:
        cogents = self._cogents_dir()

        if not (cogents / ".git").is_dir():
            info(f"Cloning cogents into {cogents}...")
            info("Using GitHub SSH auth from your local GitHub account (must have Metta-AI access).")
            self.run_command(
                ["git", "clone", COGENTS_REPO, str(cogents)],
                capture_output=False,
                non_interactive=non_interactive,
                check=True,
            )
        else:
            info("Cogents repo already cloned.")

        rel = Path("..") / ".." / "cogents"
        for link_rel, target_subdir in SYMLINKS.items():
            link = self.repo_root / link_rel
            link.parent.mkdir(parents=True, exist_ok=True)
            target = rel / target_subdir
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(target)

        success("Cogents linked.")
