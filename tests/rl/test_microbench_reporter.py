from __future__ import annotations

import json

from metta.rl.training.microbench_reporter import MicrobenchReporter, MicrobenchReporterConfig, _EpochRecord


def test_microbench_reporter_writes_artifact(tmp_path):  # noqa: ANN001
    out = tmp_path / "microbench.json"
    reporter = MicrobenchReporter(
        MicrobenchReporterConfig(warmup_epochs=1, output_path=out),
        run_metadata={"run": "test"},
    )

    # Avoid needing a full trainer context: _emit_summary_and_artifact only depends on _records.
    reporter._records = [  # type: ignore[attr-defined]
        _EpochRecord(
            epoch=1,
            agent_step=100,
            sps=1000.0,
            train_time=1.0,
            rollout_time=1.0,
            stats_time=0.1,
            rollout_env_wait_time=0.2,
            rollout_td_prep_time=0.2,
            rollout_inference_time=0.2,
            rollout_send_time=0.2,
        ),
        _EpochRecord(
            epoch=2,
            agent_step=200,
            sps=1100.0,
            train_time=1.0,
            rollout_time=1.0,
            stats_time=0.1,
            rollout_env_wait_time=0.2,
            rollout_td_prep_time=0.2,
            rollout_inference_time=0.2,
            rollout_send_time=0.2,
        ),
        _EpochRecord(
            epoch=3,
            agent_step=300,
            sps=900.0,
            train_time=1.0,
            rollout_time=1.0,
            stats_time=0.1,
            rollout_env_wait_time=0.2,
            rollout_td_prep_time=0.2,
            rollout_inference_time=0.2,
            rollout_send_time=0.2,
        ),
    ]

    reporter._emit_summary_and_artifact(status="completed")  # type: ignore[attr-defined]

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["status"] == "completed"
    assert payload["warmup_epochs"] == 1
    assert payload["run_metadata"]["run"] == "test"
    assert len(payload["records"]) == 3
    assert len(payload["effective_records"]) == 2  # epochs > warmup
    assert payload["summary"]["samples"] == 2


def test_microbench_reporter_p10_p90_short_runs_do_not_crash(tmp_path):  # noqa: ANN001
    out = tmp_path / "microbench.json"
    reporter = MicrobenchReporter(
        MicrobenchReporterConfig(warmup_epochs=0, output_path=out),
        run_metadata={"run": "test"},
    )

    reporter._records = [  # type: ignore[attr-defined]
        _EpochRecord(
            epoch=i + 1,
            agent_step=(i + 1) * 100,
            sps=1000.0 + i,
            train_time=1.0,
            rollout_time=1.0,
            stats_time=0.1,
            rollout_env_wait_time=0.2,
            rollout_td_prep_time=0.2,
            rollout_inference_time=0.2,
            rollout_send_time=0.2,
        )
        for i in range(10)
    ]

    reporter._emit_summary_and_artifact(status="completed")  # type: ignore[attr-defined]

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["summary"]["samples"] == 10
    assert "sps_p10" in payload["summary"]
    assert "sps_p90" in payload["summary"]
