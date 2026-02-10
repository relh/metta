import json
import tempfile
from pathlib import Path

from cogames.cli.mission import get_mission
from mettagrid.policy.noop import NoopPolicy
from mettagrid.policy.policy_env_interface import PolicyEnvInterface
from mettagrid.runner.rollout import single_episode_rollout
from mettagrid.util.tracer import Tracer


def test_subprocess_trace_written_to_debug_dir():
    _, env_cfg, _ = get_mission("evals.diagnostic_chest_navigation1", variants_arg=None, cogs=2)
    env_cfg.game.max_steps = 10
    num_agents = env_cfg.game.num_agents
    env_interface = PolicyEnvInterface.from_mg_cfg(env_cfg)

    policies = [NoopPolicy(env_interface)]

    with tempfile.TemporaryDirectory() as debug_dir_str:
        debug_dir = Path(debug_dir_str)
        trace_path = debug_dir / "trace.json"

        single_episode_rollout(
            policies,
            [0] * num_agents,
            env_cfg,
            seed=42,
            max_action_time_ms=10000,
            render_mode="none",
            autostart=False,
            capture_replay=False,
            trace_path=trace_path,
        )

        assert trace_path.exists()
        events = json.loads(trace_path.read_text())
        assert len(events) > 0
        event_names = {e["name"] for e in events if e.get("ph") == "X"}
        assert "env_step" in event_names


def test_executor_trace_written_to_debug_dir():
    with tempfile.TemporaryDirectory() as debug_dir_str:
        debug_dir = Path(debug_dir_str)
        trace_path = debug_dir / "setup_trace.json"

        tracer = Tracer(trace_path)
        tracer._write_process_name(Tracer.PID_EXECUTOR, "Executor", sort_index=-2)

        with tracer.span("test_span", pid=Tracer.PID_EXECUTOR):
            pass

        tracer.flush()

        assert trace_path.exists()
        events = json.loads(trace_path.read_text())
        span_events = [e for e in events if e.get("ph") == "X"]
        assert len(span_events) == 1
        assert span_events[0]["name"] == "test_span"
        assert span_events[0]["pid"] == Tracer.PID_EXECUTOR
        assert span_events[0]["ts"] > 0
