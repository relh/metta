from __future__ import annotations

from pathlib import Path

from cogames_rl_researcher.defects import build_defect_backlog, set_defect_status, submit_crash_defect


def test_submit_crash_defect_persists_and_builds_backlog(tmp_path: Path) -> None:
    store_dir = tmp_path / "defects"

    defect = submit_crash_defect(
        store_dir=store_dir,
        reporter="claude",
        command="cogames upload --name p --policy metta://policy/role_py --season beta-cogsguard",
        observed_error="authentication failed: token expired",
        context="startup upload stage",
        season="beta-cogsguard",
        policy_name="p",
    )

    assert defect.status == "open"
    assert defect.likely_owner == "auth"
    assert (store_dir / "crash_defects.jsonl").exists()
    assert (store_dir / "defect_backlog.json").exists()

    backlog = build_defect_backlog(store_dir)
    assert backlog.total_defects == 1
    assert backlog.open_defects == 1


def test_set_defect_status_updates_existing_record(tmp_path: Path) -> None:
    store_dir = tmp_path / "defects"

    defect = submit_crash_defect(
        store_dir=store_dir,
        reporter="codex",
        command="cogames scrimmage --mission cogsguard_arena.basic",
        observed_error="failed: timeout in rollout",
    )

    updated = set_defect_status(store_dir=store_dir, defect_id=defect.defect_id, status="fixed")

    assert updated.status == "fixed"
    backlog = build_defect_backlog(store_dir)
    assert backlog.status_counts["fixed"] == 1
