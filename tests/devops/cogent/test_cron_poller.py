from __future__ import annotations

import copy
import types
from datetime import datetime, timezone

import devops.cogent.cron_poller as cron_poller


def test_scan_asana_tasks_marks_failed_when_post_run_api_call_raises(monkeypatch) -> None:
    class _Ctx:
        branch = "cogent/feature"
        skill = None
        latest_comment_time = None

        def to_prompt(self) -> str:
            return "do work"

    class _Client:
        running_tag_gid = "tag-1"

        def __init__(self) -> None:
            self.post_comment_calls = 0

        @classmethod
        def from_env(cls) -> "_Client":
            return cls()

        def get_assigned_tasks(self) -> list[dict[str, str]]:
            return [{"gid": "task-1"}]

        def get_task_context(self, task_gid: str) -> _Ctx:  # noqa: ARG002
            return _Ctx()

        def add_tag(self, task_gid: str, tag_gid: str) -> None:  # noqa: ARG002
            return

        def remove_tag(self, task_gid: str, tag_gid: str) -> None:  # noqa: ARG002
            return

        def post_comment(self, task_gid: str, text: str) -> None:  # noqa: ARG002
            self.post_comment_calls += 1
            # First call is "started" status; second call is completion and fails.
            if self.post_comment_calls == 2:
                raise RuntimeError("asana post failed")

        def complete_task(self, task_gid: str) -> None:  # noqa: ARG002
            return

    monkeypatch.setenv("ASANA_TOKEN", "token")
    monkeypatch.setattr(cron_poller, "_remote_branch_exists", lambda branch: True)  # noqa: ARG005
    monkeypatch.setattr(
        cron_poller.subprocess,
        "run",
        lambda *args, **kwargs: types.SimpleNamespace(returncode=0, stdout="result", stderr=""),  # noqa: ARG005
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "asana_client",
        types.SimpleNamespace(AsanaClient=_Client),
    )

    snapshots: list[dict] = []
    monkeypatch.setattr(cron_poller, "save_state", lambda s: snapshots.append(copy.deepcopy(s)))

    state: dict = {}
    now = datetime(2026, 2, 25, 12, 0, tzinfo=timezone.utc)
    cron_poller.scan_asana_tasks(state, now)

    assert state["asana_tasks"]["task-1"]["status"] == "failed"
    assert snapshots
    assert snapshots[-1]["asana_tasks"]["task-1"]["status"] == "failed"


def test_scan_asana_invalid_branch_does_not_loop_on_poller_comment(monkeypatch) -> None:
    class _Ctx:
        branch = "azazazaz"
        skill = None

        def __init__(self, latest_comment_time: str | None):
            self.latest_comment_time = latest_comment_time

        def to_prompt(self) -> str:
            return "do work"

    class _Client:
        running_tag_gid = "tag-1"
        _latest_comment_time = "2026-02-25T22:13:00.000Z"
        _post_comment_calls = 0

        def __init__(self) -> None:
            return

        @classmethod
        def from_env(cls) -> "_Client":
            return cls()

        def get_assigned_tasks(self) -> list[dict[str, str]]:
            return [{"gid": "task-1"}]

        def get_task_context(self, task_gid: str) -> _Ctx:  # noqa: ARG002
            return _Ctx(self.__class__._latest_comment_time)

        def post_comment(self, task_gid: str, text: str) -> None:  # noqa: ARG002
            self.__class__._post_comment_calls += 1
            # Simulate Asana advancing latest comment timestamp to the poller-authored comment.
            self.__class__._latest_comment_time = f"2026-02-25T22:13:0{self.__class__._post_comment_calls}.000Z"

        def add_tag(self, task_gid: str, tag_gid: str) -> None:  # noqa: ARG002
            return

        def remove_tag(self, task_gid: str, tag_gid: str) -> None:  # noqa: ARG002
            return

        def complete_task(self, task_gid: str) -> None:  # noqa: ARG002
            return

    monkeypatch.setenv("ASANA_TOKEN", "token")
    monkeypatch.setattr(cron_poller, "_remote_branch_exists", lambda branch: False)  # noqa: ARG005
    monkeypatch.setitem(
        __import__("sys").modules,
        "asana_client",
        types.SimpleNamespace(AsanaClient=_Client),
    )

    state: dict = {}
    now = datetime(2026, 2, 25, 22, 13, tzinfo=timezone.utc)

    cron_poller.scan_asana_tasks(state, now)
    first_seen = state["asana_tasks"]["task-1"]["last_comment_seen"]

    # Second scan should not re-post failure comment because poller's own comment is marked seen.
    cron_poller.scan_asana_tasks(state, now)
    second_seen = state["asana_tasks"]["task-1"]["last_comment_seen"]

    assert first_seen == second_seen
    assert state["asana_tasks"]["task-1"]["status"] == "failed"
    assert _Client._post_comment_calls == 1


def test_scan_asana_tasks_continues_when_one_task_context_fetch_fails(monkeypatch) -> None:
    class _Ctx:
        branch = "cogent/feature"
        skill = None
        latest_comment_time = None

        def to_prompt(self) -> str:
            return "do work"

    class _Client:
        running_tag_gid = "tag-1"

        @classmethod
        def from_env(cls) -> "_Client":
            return cls()

        def get_assigned_tasks(self) -> list[dict[str, str]]:
            return [{"gid": "task-bad"}, {"gid": "task-good"}]

        def get_task_context(self, task_gid: str) -> _Ctx:
            if task_gid == "task-bad":
                raise RuntimeError("broken context")
            return _Ctx()

        def add_tag(self, task_gid: str, tag_gid: str) -> None:  # noqa: ARG002
            return

        def remove_tag(self, task_gid: str, tag_gid: str) -> None:  # noqa: ARG002
            return

        def post_comment(self, task_gid: str, text: str) -> None:  # noqa: ARG002
            return

        def complete_task(self, task_gid: str) -> None:  # noqa: ARG002
            return

    monkeypatch.setenv("ASANA_TOKEN", "token")
    monkeypatch.setattr(cron_poller, "_remote_branch_exists", lambda branch: True)  # noqa: ARG005
    monkeypatch.setattr(
        cron_poller.subprocess,
        "run",
        lambda *args, **kwargs: types.SimpleNamespace(returncode=0, stdout="result", stderr=""),  # noqa: ARG005
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "asana_client",
        types.SimpleNamespace(AsanaClient=_Client),
    )

    snapshots: list[dict] = []
    monkeypatch.setattr(cron_poller, "save_state", lambda s: snapshots.append(copy.deepcopy(s)))

    state: dict = {}
    now = datetime(2026, 2, 25, 12, 0, tzinfo=timezone.utc)
    cron_poller.scan_asana_tasks(state, now)

    assert "task-bad" not in state.get("asana_tasks", {})
    assert state["asana_tasks"]["task-good"]["status"] == "completed"
    assert snapshots


def test_tick_saves_state_when_asana_scan_raises(monkeypatch) -> None:
    state = {"last_run": {}, "completed_once": []}
    monkeypatch.setattr(cron_poller, "load_state", lambda: state)
    monkeypatch.setattr(cron_poller, "prune_stale_worktrees", lambda: None)
    monkeypatch.setattr(cron_poller, "load_schedule_jobs", lambda: [])
    monkeypatch.setattr(cron_poller, "list_remote_branches", lambda repo_dir: [])  # noqa: ARG005
    monkeypatch.setattr(cron_poller, "scan_asana_tasks", lambda s, now: (_ for _ in ()).throw(RuntimeError("boom")))

    snapshots: list[dict] = []
    monkeypatch.setattr(cron_poller, "save_state", lambda s: snapshots.append(copy.deepcopy(s)))

    cron_poller.tick()

    assert snapshots
    assert snapshots[-1] == state


def test_tick_keeps_failed_one_shot_branch_job(monkeypatch) -> None:
    state = {"last_run": {}, "completed_once": []}
    monkeypatch.setattr(cron_poller, "load_state", lambda: state)
    monkeypatch.setattr(cron_poller, "prune_stale_worktrees", lambda: None)
    monkeypatch.setattr(cron_poller, "load_schedule_jobs", lambda: [])
    monkeypatch.setattr(cron_poller, "scan_asana_tasks", lambda s, now: None)  # noqa: ARG005
    monkeypatch.setattr(cron_poller, "list_remote_branches", lambda repo_dir: ["origin/cogent/test"])  # noqa: ARG005
    monkeypatch.setattr(cron_poller, "list_branch_jobs", lambda repo_dir, ref: [".agent/jobs/task.md"])  # noqa: ARG005
    monkeypatch.setattr(
        cron_poller,
        "read_branch_file",
        lambda repo_dir, ref, path: "---\nschedule: once\nskill: cb.review-main\n---\n",  # noqa: ARG005
    )
    monkeypatch.setattr(cron_poller, "run_agent_job", lambda **kwargs: False)

    deleted: list[tuple[str, str]] = []
    monkeypatch.setattr(
        cron_poller,
        "delete_branch_job_file",
        lambda repo_dir, branch, file_path: deleted.append((branch, file_path)),  # noqa: ARG005
    )

    snapshots: list[dict] = []
    monkeypatch.setattr(cron_poller, "save_state", lambda s: snapshots.append(copy.deepcopy(s)))

    cron_poller.tick()

    assert deleted == []
    assert "branch:cogent/test:task.md" not in state["completed_once"]
    assert snapshots


def test_tick_once_branch_job_failure_adds_delayed_retry(monkeypatch) -> None:
    state = {"last_run": {}, "completed_once": []}
    monkeypatch.setattr(cron_poller, "load_state", lambda: state)
    monkeypatch.setattr(cron_poller, "prune_stale_worktrees", lambda: None)
    monkeypatch.setattr(cron_poller, "load_schedule_jobs", lambda: [])
    monkeypatch.setattr(cron_poller, "scan_asana_tasks", lambda s, now: None)  # noqa: ARG005
    monkeypatch.setattr(cron_poller, "list_remote_branches", lambda repo_dir: ["origin/cogent/test"])  # noqa: ARG005
    monkeypatch.setattr(cron_poller, "list_branch_jobs", lambda repo_dir, ref: [".agent/jobs/task.md"])  # noqa: ARG005
    content = "---\nschedule: once\nskill: cb.review-main\n---\n"
    monkeypatch.setattr(cron_poller, "read_branch_file", lambda repo_dir, ref, path: content)  # noqa: ARG005
    monkeypatch.setattr(cron_poller, "run_agent_job", lambda **kwargs: False)
    monkeypatch.setattr(cron_poller, "delete_branch_job_file", lambda *args, **kwargs: None)

    cron_poller.tick()

    job_id = "branch:cogent/test:task.md"
    entry = state["branch_once_retries"][job_id]
    assert entry["failed_attempts"] == 1
    assert entry["exhausted"] is False
    assert entry["next_retry_at"] is not None


def test_tick_once_branch_job_retry_gate_and_exhaustion(monkeypatch) -> None:
    content = "---\nschedule: once\nskill: cb.review-main\n---\n"
    job_id = "branch:cogent/test:task.md"
    job_fingerprint = cron_poller._job_fingerprint(content)
    state = {
        "last_run": {},
        "completed_once": [],
        "branch_once_retries": {
            job_id: {
                "job_fingerprint": job_fingerprint,
                "failed_attempts": 1,
                "last_failed_at": "2026-02-25T00:00:00+00:00",
                "next_retry_at": "2999-01-01T00:00:00+00:00",
                "exhausted": False,
            }
        },
    }
    monkeypatch.setattr(cron_poller, "load_state", lambda: state)
    monkeypatch.setattr(cron_poller, "prune_stale_worktrees", lambda: None)
    monkeypatch.setattr(cron_poller, "load_schedule_jobs", lambda: [])
    monkeypatch.setattr(cron_poller, "scan_asana_tasks", lambda s, now: None)  # noqa: ARG005
    monkeypatch.setattr(cron_poller, "list_remote_branches", lambda repo_dir: ["origin/cogent/test"])  # noqa: ARG005
    monkeypatch.setattr(cron_poller, "list_branch_jobs", lambda repo_dir, ref: [".agent/jobs/task.md"])  # noqa: ARG005
    monkeypatch.setattr(cron_poller, "read_branch_file", lambda repo_dir, ref, path: content)  # noqa: ARG005
    monkeypatch.setattr(cron_poller, "delete_branch_job_file", lambda *args, **kwargs: None)

    calls: list[dict] = []
    monkeypatch.setattr(cron_poller, "run_agent_job", lambda **kwargs: calls.append(kwargs) or False)

    # Not yet due for retry.
    cron_poller.tick()
    assert calls == []

    # Make retries immediately due and consume remaining attempts.
    state["branch_once_retries"][job_id]["next_retry_at"] = "2000-01-01T00:00:00+00:00"
    state["branch_once_retries"][job_id]["failed_attempts"] = 2
    cron_poller.tick()
    assert len(calls) == 1
    assert state["branch_once_retries"][job_id]["failed_attempts"] == 3
    assert state["branch_once_retries"][job_id]["exhausted"] is True
    assert state["branch_once_retries"][job_id]["next_retry_at"] is None
