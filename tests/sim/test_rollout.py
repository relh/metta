from __future__ import annotations

import time
from typing import Any

import mettagrid.simulator.rollout as rollout_mod
from mettagrid import MettaGridConfig
from mettagrid.simulator.rollout import Rollout


class _StubPolicy:
    def __init__(self, action: Any, *, sleep_s: float = 0.0):
        self._action = action
        self._sleep_s = sleep_s
        self._infos: dict[str, Any] = {}

    @property
    def infos(self) -> dict[str, Any]:
        return self._infos

    def reset(self) -> None:
        pass

    def step(self, obs: Any) -> Any:
        if self._sleep_s:
            time.sleep(self._sleep_s)
        return self._action

    def can_step_group(self, policies: list[_StubPolicy]) -> bool:
        return True

    def step_group(self, observations: list[tuple[int, Any]]) -> list[Any]:
        if self._sleep_s:
            time.sleep(self._sleep_s)
        return [self._action for _ in observations]


class _RecordingSpan:
    def __init__(self, tracer: _RecordingTracer, name: str, pid: int | None, metadata: dict[str, Any]):
        self._tracer = tracer
        self._name = name
        self._pid = pid
        self._metadata = metadata
        self._start_ns = 0

    def set(self, **metadata: Any) -> None:
        self._metadata.update(metadata)

    def __enter__(self) -> _RecordingSpan:
        self._start_ns = time.time_ns()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self._tracer.record_span(
            self._name,
            self._start_ns,
            time.time_ns() - self._start_ns,
            pid=self._pid,
            **self._metadata,
        )


class _RecordingTracer:
    def __init__(self):
        self.spans: list[dict[str, Any]] = []

    def span(self, name: str, pid: int | None = None, **metadata: Any) -> _RecordingSpan:
        return _RecordingSpan(self, name, pid, metadata)

    def record_span(
        self,
        name: str,
        start_ns: int,
        duration_ns: int,
        pid: int | None = None,
        **metadata: Any,
    ) -> None:
        self.spans.append(
            {
                "name": name,
                "start_ns": start_ns,
                "duration_ns": duration_ns,
                "pid": pid,
                "metadata": metadata,
            }
        )

    def flush(self) -> None:
        pass


def test_group_executor_worker_count_is_bounded(monkeypatch) -> None:
    env_cfg = MettaGridConfig.EmptyRoom(num_agents=5)
    env_cfg.game.max_steps = 1
    action = env_cfg.game.actions.noop.Noop()

    created: dict[str, int] = {}

    class _InlineFuture:
        def __init__(self, result: Any):
            self._result = result

        def result(self) -> Any:
            return self._result

    class _RecordingExecutor:
        def __init__(self, *, max_workers: int):
            created["max_workers"] = max_workers

        def submit(self, fn: Any, *args: Any, **kwargs: Any) -> _InlineFuture:
            return _InlineFuture(fn(*args, **kwargs))

        def shutdown(self, wait: bool = True, cancel_futures: bool = False) -> None:
            pass

    monkeypatch.setattr(rollout_mod.os, "cpu_count", lambda: 2)
    monkeypatch.setattr(rollout_mod, "ThreadPoolExecutor", _RecordingExecutor)

    policies = [_StubPolicy(action) for _ in range(env_cfg.game.num_agents)]
    rollout = Rollout(env_cfg, policies, policy_group_keys=list(range(env_cfg.game.num_agents)))

    rollout.run_until_done()

    assert created["max_workers"] == 2


def test_grouped_agent_step_spans_cover_batched_step_latency() -> None:
    env_cfg = MettaGridConfig.EmptyRoom(num_agents=2)
    env_cfg.game.max_steps = 1
    action = env_cfg.game.actions.noop.Noop()
    tracer = _RecordingTracer()
    policies = [_StubPolicy(action, sleep_s=0.02) for _ in range(env_cfg.game.num_agents)]

    rollout = Rollout(env_cfg, policies, tracer=tracer, policy_group_keys=[0, 0])
    rollout.run_until_done()

    agent_step_spans = [span for span in tracer.spans if span["name"] == "agent_step"]
    assert len(agent_step_spans) == 2
    assert all(span["duration_ns"] >= 15_000_000 for span in agent_step_spans)
    assert all(span["metadata"]["elapsed_ms"] >= 15 for span in agent_step_spans)
