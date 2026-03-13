from pathlib import Path

from metta.setup.cogents_sync import missing_shared_skills
from metta.setup.components.base import SetupModule
from metta.setup.registry import register_module
from metta.setup.utils import info, success, warning

COGENTS_REPO = "git@github.com:Metta-AI/cogents.git"

SYMLINKS: dict[str, str] = {
    ".claude/skills": "skills",
    ".codex/skills": "skills",
    ".cursor/skills": "skills",
    ".cursor/agents": "subagents",
    ".agent/prompts": "prompts",
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

    def _sync_existing_checkout(self, cogents: Path, non_interactive: bool) -> None:
        branch = self.run_command(
            ["git", "-C", str(cogents), "branch", "--show-current"],
            capture_output=True,
            non_interactive=non_interactive,
        ).stdout.strip()
        if branch != "main":
            warning(f"Cogents repo is on branch '{branch or 'detached'}'; skipping auto-update.")
            return

        status = self.run_command(
            ["git", "-C", str(cogents), "status", "--short"],
            capture_output=True,
            non_interactive=non_interactive,
        ).stdout.strip()
        if status:
            warning("Cogents repo has local changes; skipping auto-update.")
            return

        fetch = self.run_command(
            ["git", "-C", str(cogents), "fetch", "origin"],
            capture_output=True,
            check=False,
            non_interactive=non_interactive,
        )
        if fetch.returncode != 0:
            warning("Failed to fetch cogents origin; leaving existing checkout as-is.")
            return

        behind = int(
            self.run_command(
                ["git", "-C", str(cogents), "rev-list", "--count", "HEAD..origin/main"],
                capture_output=True,
                non_interactive=non_interactive,
            ).stdout.strip()
            or "0"
        )
        if behind == 0:
            info("Cogents repo already up to date.")
            return

        info(f"Fast-forwarding cogents by {behind} commit(s)...")
        self.run_command(
            ["git", "-C", str(cogents), "merge", "--ff-only", "origin/main"],
            capture_output=False,
            non_interactive=non_interactive,
        )

    def _ensure_shared_skills_exist(self, cogents: Path) -> None:
        missing = missing_shared_skills(self.repo_root, cogents / "skills")
        if missing:
            missing_list = ", ".join(missing)
            raise RuntimeError(
                "Cogents checkout is missing shared skills referenced by "
                f".cursor/rules/skills.mdc: {missing_list}. "
                "Run ./scripts/setup-cogents.sh after updating the sibling cogents clone."
            )

    def check_installed(self) -> bool:
        cogents = self._cogents_dir()
        if not (cogents / ".git").is_dir():
            return False
        for link_rel in SYMLINKS:
            link = self.repo_root / link_rel
            if not link.is_symlink():
                return False
        return not missing_shared_skills(self.repo_root, cogents / "skills")

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
            self._sync_existing_checkout(cogents, non_interactive=non_interactive)

        rel = Path("..") / ".." / "cogents"
        for link_rel, target_subdir in SYMLINKS.items():
            link = self.repo_root / link_rel
            link.parent.mkdir(parents=True, exist_ok=True)
            target = rel / target_subdir
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(target)

        self._ensure_shared_skills_exist(cogents)
        success("Cogents linked.")
