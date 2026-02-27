"""Local and Remote Job runner used by GitHub Actions."""

from __future__ import annotations

import json
import threading
import time
from collections import defaultdict
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from datetime import datetime, timedelta
from pathlib import Path

import wandb

from devops.runners.job import ExecutorType, Job, JobHandle, JobStatus
from devops.runners.metta_constants import METTA_WANDB_ENTITY, METTA_WANDB_PROJECT


def _now() -> datetime:
    return datetime.now()


def _duration_s(started_at: datetime, completed_at: datetime) -> float:
    return (completed_at - started_at).total_seconds()


class _AcceptanceEvaluator:
    def __init__(self) -> None:
        self._api: wandb.Api | None = None

    def evaluate(self, job: Job) -> None:
        if job.status != JobStatus.SUCCEEDED:
            return
        if not job.wandb_run_name:
            return
        if self._api is None:
            self._api = wandb.Api()
        try:
            run = self._api.run(f"{METTA_WANDB_ENTITY}/{METTA_WANDB_PROJECT}/{job.wandb_run_name}")
            job.metrics = dict(run.summary)
        except Exception as e:
            job.acceptance_passed = False
            job.error = f"WandB fetch failed: {e}"
            return

        if not job.acceptance:
            return
        job.acceptance_passed = self._passes_acceptance(job)
        if not job.acceptance_passed:
            job.error = "Acceptance criteria not met"

    def _passes_acceptance(self, job: Job) -> bool:
        failures: list[str] = []
        for c in job.acceptance:
            actual = job.metrics.get(c.metric)
            if actual is None:
                job.criterion_results[c.metric] = False
                failures.append(f"{c.metric}: missing (required {c.operator} {c.threshold})")
                continue

            passed = False
            if c.operator == "in":
                assert isinstance(c.threshold, tuple)
                low, high = c.threshold
                passed = low <= actual <= high
            else:
                assert isinstance(c.threshold, (int, float))
                threshold = float(c.threshold)
                match c.operator:
                    case ">=":
                        passed = actual >= threshold
                    case ">":
                        passed = actual > threshold
                    case "<=":
                        passed = actual <= threshold
                    case "<":
                        passed = actual < threshold
                    case "==":
                        passed = actual == threshold

            job.criterion_results[c.metric] = passed
            if not passed:
                failures.append(f"{c.metric}: {actual:.4g} (required {c.operator} {c.threshold})")

        if failures:
            job.acceptance_failures = failures
            return False
        return True


class Runner:
    _STATUS_EVERY = timedelta(minutes=10)
    _REMOTE_POLL_EVERY_S = 5.0
    _REMOTE_NOT_FOUND_GRACE = timedelta(minutes=5)

    def __init__(self, state_dir: Path):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir = self.state_dir / "logs"
        self.logs_dir.mkdir(exist_ok=True)

        self.jobs: dict[str, Job] = {}
        self._handles: dict[str, JobHandle] = {}
        self._executor: ThreadPoolExecutor | None = None
        self._output_lock = threading.Lock()
        self._acceptance = _AcceptanceEvaluator()

        self._dependents: dict[str, list[str]] = {}
        self._remaining_deps: dict[str, int] = {}

        self._remote_not_found_deadline: dict[str, datetime] = {}

    def add_job(self, job: Job) -> None:
        self.jobs[job.name] = job

    def run_all(self) -> dict[str, Job]:
        self._executor = ThreadPoolExecutor(max_workers=min(32, max(1, len(self.jobs))))
        self._build_dependency_index()

        last_status = _now()
        next_remote_poll = time.monotonic()

        try:
            while self._has_incomplete_jobs():
                self._start_ready_jobs()

                if _now() - last_status >= self._STATUS_EVERY:
                    self._print_status_summary()
                    last_status = _now()

                self._drain_completed_futures()

                if self._has_remote_running():
                    now_mono = time.monotonic()
                    if now_mono >= next_remote_poll:
                        self._poll_remote_jobs()
                        next_remote_poll = now_mono + self._REMOTE_POLL_EVERY_S

                self._wait_for_progress(next_remote_poll)
        finally:
            if self._executor is not None:
                self._executor.shutdown(wait=True)
            self._executor = None

        return self.jobs

    def _build_dependency_index(self) -> None:
        self._dependents = {name: [] for name in self.jobs}
        self._remaining_deps = {name: 0 for name in self.jobs}

        for job in self.jobs.values():
            missing = [d for d in job.dependencies if d not in self.jobs]
            if missing:
                self._skip_job(job, f"Missing dependency: {missing[0]}")
                continue

            self._remaining_deps[job.name] = len(job.dependencies)
            for dep in job.dependencies:
                self._dependents[dep].append(job.name)

        for job in self.jobs.values():
            if job.status != JobStatus.NOT_STARTED:
                continue
            if any(self.jobs[d].status in (JobStatus.FAILED, JobStatus.SKIPPED) for d in job.dependencies):
                dep = next(d for d in job.dependencies if self.jobs[d].status in (JobStatus.FAILED, JobStatus.SKIPPED))
                self._skip_job(job, f"Dependency {self.jobs[dep].status.value.lower()}: {dep}")

    def _has_incomplete_jobs(self) -> bool:
        return any(j.status in (JobStatus.NOT_STARTED, JobStatus.RUNNING) for j in self.jobs.values())

    def _has_remote_running(self) -> bool:
        return any(j.status == JobStatus.RUNNING and j.is_remote for j in self.jobs.values())

    def _ready_jobs(self) -> list[Job]:
        ready = []
        for job in self.jobs.values():
            if job.status != JobStatus.NOT_STARTED:
                continue
            if self._remaining_deps.get(job.name, 0) != 0:
                continue
            ready.append(job)
        return ready

    def _start_ready_jobs(self) -> None:
        for job in self._ready_jobs():
            self._start_job(job)

    def _start_job(self, job: Job) -> None:
        assert self._executor is not None

        job.status = JobStatus.RUNNING
        job.started_at = _now()
        job.logs_path = str(self.logs_dir / f"{job.name}.log")
        self._emit_check_event(
            "CHECK_START",
            job,
            executor=job.executor.ex_type.value,
            is_remote=job.is_remote,
            timeout_s=job.timeout_s,
            dependencies=job.dependencies,
            command=job.cmd,
            log_path=job.logs_path,
            check_group=job.metadata.get("check_group"),
            lifecycle=job.metadata.get("lifecycle"),
        )

        if job.is_remote:
            self._print(f"[{job.name}] Launching remote: {' '.join(job.cmd)}")
        else:
            self._print(f"[{job.name}] Starting: {' '.join(job.cmd)}")

        handle = job.executor.launch(job, Path(job.logs_path), self._executor)
        self._handles[job.name] = handle

    def _drain_completed_futures(self) -> None:
        completed: list[tuple[str, Future]] = []
        for name, handle in list(self._handles.items()):
            for f in handle.futures:
                if f.done():
                    completed.append((name, f))
        for name, future in completed:
            self._handles.pop(name, None)
            self._on_future_done(self.jobs[name], future)

    def _on_future_done(self, job: Job, future: Future) -> None:
        callback_result = job.executor.on_future_done(job, future)

        if callback_result is not None:
            return self._finish(
                callback_result.job, callback_result.status, callback_result.exit_code, error=callback_result.error
            )

        if job.remote_id:
            self._remote_not_found_deadline[job.name] = _now() + self._REMOTE_NOT_FOUND_GRACE
            self._emit_check_event("CHECK_REMOTE_LAUNCHED", job, remote_id=job.remote_id)
            self._print(f"[{job.name}] Launched: job_id={job.remote_id}")
            return
        else:
            raise ValueError(
                "job.executor.on_future_done did not return a JobResult therefore "
                "expected job.remote_id to be set for remote polling, found None."
            )

    def _poll_remote_jobs(self) -> None:
        running = [j for j in self.jobs.values() if j.status == JobStatus.RUNNING and j.is_remote]
        if not running:
            return

        now = _now()

        # Check timeouts
        for job in running:
            if job.started_at and now - job.started_at > timedelta(seconds=job.timeout_s):
                self._finish(job, JobStatus.FAILED, 124, f"Timeout after {job.timeout_s}s")
                job.executor.cancel(job)

        running = [j for j in self.jobs.values() if j.status == JobStatus.RUNNING and j.is_remote]
        if not running:
            return

        running_jobs_per_executor: defaultdict[ExecutorType, list[Job]] = defaultdict(list)

        for j in running:
            running_jobs_per_executor[j.executor.ex_type].append(j)

        for k in running_jobs_per_executor:
            executor = running_jobs_per_executor[k][0].executor
            try:
                result = executor.poll(running_jobs_per_executor[k], self._remote_not_found_deadline)
            except Exception as e:
                self._print(f"[WARN]: {type(executor).__name__} Failed to poll remote job status (will retry): {e}")
                continue

            if result is None:
                continue

            for r in result:
                self._finish(r.job, r.status, r.exit_code, r.error)

    def _finish(self, job: Job, status: JobStatus, exit_code: int, error: str | None = None) -> None:
        job.status = status
        job.exit_code = exit_code
        job.error = error
        job.completed_at = _now()
        if job.started_at:
            job.duration_s = _duration_s(job.started_at, job.completed_at)

        if status == JobStatus.SUCCEEDED:
            self._acceptance.evaluate(job)
            if job.acceptance_passed is False:
                result = f"FAILED: {job.error or 'Acceptance criteria not met'}"
            else:
                result = "PASSED"
        else:
            result = f"FAILED: {job.error or exit_code}"

        duration = f"{job.duration_s:.0f}s" if job.duration_s is not None else "-"
        self._print(f"[{job.name}] {result} (duration={duration})")
        self._emit_check_event(
            "CHECK_END",
            job,
            status=job.status.value,
            result=result,
            exit_code=job.exit_code,
            duration_s=job.duration_s,
            acceptance_passed=job.acceptance_passed,
            error=job.error,
            log_path=job.logs_path,
        )

        self._on_job_terminal(job)

    def _on_job_terminal(self, job: Job) -> None:
        for dependent_name in self._dependents.get(job.name, []):
            dependent = self.jobs[dependent_name]
            if dependent.status != JobStatus.NOT_STARTED:
                continue

            if job.status in (JobStatus.FAILED, JobStatus.SKIPPED):
                self._skip_job(dependent, f"Dependency {job.status.value.lower()}: {job.name}")
                continue

            self._remaining_deps[dependent_name] -= 1

    def _skip_job(self, job: Job, reason: str) -> None:
        job.status = JobStatus.SKIPPED
        job.exit_code = 0
        job.error = reason
        self._print(f"[{job.name}] SKIPPED: {reason}")
        self._emit_check_event("CHECK_SKIP", job, reason=reason)
        self._on_job_terminal(job)

    def _emit_check_event(self, event: str, job: Job, **fields: object) -> None:
        payload = {
            "timestamp": _now().isoformat(timespec="seconds"),
            "event": event,
            "job_name": job.name,
        }
        payload.update(fields)
        self._print(f"[CHECK_EVENT] {json.dumps(payload, sort_keys=True, default=str)}")

    def _wait_for_progress(self, next_remote_poll: float) -> None:
        futures: list[Future] = []
        for handle in self._handles.values():
            futures.extend(handle.futures)
        if not futures:
            time.sleep(max(0.0, min(0.5, next_remote_poll - time.monotonic())))
            return

        timeout = max(0.0, min(0.5, next_remote_poll - time.monotonic()))
        wait(futures, timeout=timeout, return_when=FIRST_COMPLETED)

    def _print(self, msg: str) -> None:
        with self._output_lock:
            print(msg, flush=True)

    def _print_status_summary(self) -> None:
        ts = _now().strftime("%Y-%m-%d %H:%M:%S")
        self._print(f"\n[{ts}] === Status Summary ===")
        now = _now()
        for job in self.jobs.values():
            elapsed = ""
            if job.started_at and job.status == JobStatus.RUNNING:
                elapsed = f" ({int((now - job.started_at).total_seconds())}s)"
            remote = f" [remote:{job.remote_id}]" if job.remote_id else ""
            self._print(f"  {job.name}: {job.status.value}{elapsed}{remote}")
        self._print("")
