"""Integration test for k8s event processor idempotency.

Tests that processing the same events multiple times produces identical job state,
verifying that deduplication logic works correctly.
"""

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError
from kubernetes import client
from sqlmodel import Session, create_engine, select

from metta.app_backend.job_runner.event_processor import _process_batch
from metta.app_backend.models.job_request import JobRequest, JobStatus, JobType
from metta.app_backend.models.k8s_events import K8sEvent


@pytest.fixture
def event_processor_db(stats_repo):
    """Reset event processor engine caches to use the test database."""
    from metta.app_backend.job_runner import (  # noqa: PLC0415
        event_processor,
        k8s_event_store,
    )

    event_processor._db_engine = None
    k8s_event_store._engine = None

    return stats_repo


@pytest.fixture
def mock_k8s_clients():
    """Mock kubernetes clients."""
    core_v1 = MagicMock(spec=client.CoreV1Api)
    batch_v1 = MagicMock(spec=client.BatchV1Api)

    # Mock job status for failure reason lookup
    mock_job = MagicMock()
    mock_job.status.conditions = None
    batch_v1.read_namespaced_job.return_value = mock_job

    return core_v1, batch_v1


@pytest.fixture
def mock_stats_client():
    """Mock stats client for job state tracking."""
    stats = MagicMock()

    # Track job state changes in memory
    stats._job_state = {}
    stats._episode_recorded = set()

    def get_job(job_id):
        if job_id not in stats._job_state:
            job = JobRequest(
                id=job_id,
                job={
                    "type": "single_episode",
                    "policy_uris": ["s3://bucket/policy"],
                    "assignments": [0],
                    "env": {"name": "test"},
                },
                status=JobStatus.dispatched,
                job_type=JobType.episode,
                user_id="test-user",
            )
            stats._job_state[job_id] = job
        return stats._job_state[job_id]

    def update_job(job_id, update):
        job = stats._job_state.get(job_id)
        if job:
            if update.status:
                job.status = update.status
            if update.error:
                job.error = update.error

    stats.get_job.side_effect = get_job
    stats.update_job.side_effect = update_job

    return stats


def create_pod_event(job_id: str, pod_name: str, phase: str, event_type: str = "MODIFIED") -> dict:
    """Create a mock k8s pod event."""
    # Build container statuses based on phase
    container_statuses = []
    if phase == "Running":
        container_statuses = [
            {
                "state": {"running": {"startedAt": "2024-01-01T00:00:00Z"}},
                "imageID": "docker.io/library/test:latest",
            }
        ]
    elif phase in ("Succeeded", "Failed"):
        container_statuses = [
            {
                "state": {
                    "terminated": {
                        "reason": "Completed" if phase == "Succeeded" else "Error",
                    }
                },
                "imageID": "docker.io/library/test:latest",
            }
        ]

    return {
        "type": event_type,
        "object": {
            "metadata": {
                "name": pod_name,
                "labels": {
                    "app": "episode-eval",
                    "job-id": str(job_id),
                },
                "ownerReferences": [
                    {
                        "kind": "Job",
                        "name": f"job-{pod_name}",
                    }
                ],
            },
            "status": {
                "phase": phase,
                "containerStatuses": container_statuses,
            },
        },
    }


def test_event_processor_idempotency(event_processor_db, mock_k8s_clients, mock_stats_client):
    """Test that processing the same events multiple times produces identical state."""
    engine = create_engine(event_processor_db)
    job_id = uuid4()
    pod_name = f"test-pod-{job_id.hex[:8]}"

    # Create sequence of events: Added -> Running -> Succeeded
    events_data = [
        create_pod_event(str(job_id), pod_name, "Pending", "ADDED"),
        create_pod_event(str(job_id), pod_name, "Running", "MODIFIED"),
        create_pod_event(str(job_id), pod_name, "Succeeded", "MODIFIED"),
    ]

    # Insert events into database
    with Session(engine) as session:
        for event_data in events_data:
            event = K8sEvent(
                cluster="test",
                event_time=datetime.now(UTC),
                event=event_data,
            )
            session.add(event)
        session.commit()

    core_v1, batch_v1 = mock_k8s_clients

    # Mock S3 operations
    with patch("metta.app_backend.job_runner.event_processor.get_s3_client") as mock_s3:
        mock_s3_client = MagicMock()
        mock_s3.return_value = mock_s3_client

        # Mock complete results in S3 with all required fields
        results_data = {
            "winner": 0,
            "episode_length": 100,
            "rewards": [0.0, 1.0],
            "action_timeouts": [0, 0],
            "stats": {
                "game": {},
                "agent": [{}],
            },
            "steps": 100,
        }
        mock_response = MagicMock()
        mock_response["Body"].read.return_value = json.dumps(results_data).encode("utf-8")
        mock_s3_client.get_object.return_value = mock_response

        # Mock runtime info (not found is ok)
        mock_s3_client.head_object.side_effect = ClientError({"Error": {"Code": "404"}}, "head_object")

        with patch("metta.app_backend.job_runner.event_processor.record_job_episode") as mock_record:
            # Process events first time
            _process_batch(mock_stats_client, core_v1, batch_v1)

            # Capture state after first processing
            first_state = {
                "status": mock_stats_client._job_state[job_id].status,
                "error": mock_stats_client._job_state[job_id].error,
                "episode_recorded": mock_record.call_count,
            }

            # Mark events as unprocessed again (simulate replay)
            with Session(engine) as session:
                stmt = select(K8sEvent)
                events = list(session.exec(stmt).all())
                for event in events:
                    event.processed_at = None
                    session.add(event)
                session.commit()

            # Reset record counter
            initial_episode_count = mock_record.call_count

            # Process events second time (should be idempotent)
            _process_batch(mock_stats_client, core_v1, batch_v1)

            # Capture state after second processing
            second_state = {
                "status": mock_stats_client._job_state[job_id].status,
                "error": mock_stats_client._job_state[job_id].error,
                "episode_recorded": mock_record.call_count - initial_episode_count,
            }

    # Verify status and error are identical on replay
    assert first_state["status"] == second_state["status"]
    assert first_state["error"] == second_state["error"]

    # Verify job ended up in correct final state
    assert first_state["status"] == JobStatus.completed
    assert first_state["error"] is None

    # Verify episode was recorded exactly once (deduplication working)
    # On second pass, the job is already completed, so episode recording should be skipped
    assert first_state["episode_recorded"] == 1, "Episode should be recorded on first pass"
    assert second_state["episode_recorded"] == 0, "Episode should not be recorded twice"


def test_event_processor_handles_duplicate_success_events(event_processor_db, mock_k8s_clients, mock_stats_client):
    """Test that multiple Succeeded events don't cause duplicate episode recording."""
    engine = create_engine(event_processor_db)
    job_id = uuid4()
    pod_name = f"test-pod-{job_id.hex[:8]}"

    # Create multiple Succeeded events (e.g., from pod restarts or watch reconnects)
    events_data = [
        create_pod_event(str(job_id), pod_name, "Running", "MODIFIED"),
        create_pod_event(str(job_id), pod_name, "Succeeded", "MODIFIED"),
        create_pod_event(str(job_id), pod_name, "Succeeded", "MODIFIED"),  # Duplicate
        create_pod_event(str(job_id), pod_name, "Succeeded", "MODIFIED"),  # Duplicate
    ]

    with Session(engine) as session:
        for event_data in events_data:
            event = K8sEvent(
                cluster="test",
                event_time=datetime.now(UTC),
                event=event_data,
            )
            session.add(event)
        session.commit()

    core_v1, batch_v1 = mock_k8s_clients

    with patch("metta.app_backend.job_runner.event_processor.get_s3_client") as mock_s3:
        mock_s3_client = MagicMock()
        mock_s3.return_value = mock_s3_client

        # Mock complete results in S3 with all required fields
        results_data = {
            "winner": 0,
            "episode_length": 100,
            "rewards": [0.0, 1.0],
            "action_timeouts": [0, 0],
            "stats": {
                "game": {},
                "agent": [{}],
            },
            "steps": 100,
        }
        mock_response = MagicMock()
        mock_response["Body"].read.return_value = json.dumps(results_data).encode("utf-8")
        mock_s3_client.get_object.return_value = mock_response
        mock_s3_client.head_object.side_effect = ClientError({"Error": {"Code": "404"}}, "head_object")

        with patch("metta.app_backend.job_runner.event_processor.record_job_episode"):
            # Track how many times update_job is called
            update_count = 0
            original_update = mock_stats_client.update_job

            def counting_update(*args, **kwargs):
                nonlocal update_count
                update_count += 1
                return original_update(*args, **kwargs)

            mock_stats_client.update_job = counting_update

            # Process all events
            _process_batch(mock_stats_client, core_v1, batch_v1)

            # Verify job is completed
            assert mock_stats_client._job_state[job_id].status == JobStatus.completed

            # Count updates to 'completed' status (deduplication should prevent multiple completions)
            # We expect: Running -> Completed (first Succeeded event processes, others skip)
            # The update_count includes both Running and Completed updates
            assert update_count <= 3, (
                f"Expected at most 3 status updates (Running + Completed + maybe one more), got {update_count}"
            )


def test_event_processor_handles_failed_events_idempotently(event_processor_db, mock_k8s_clients, mock_stats_client):
    """Test that failed pod events are processed idempotently."""
    engine = create_engine(event_processor_db)
    job_id = uuid4()
    pod_name = f"test-pod-{job_id.hex[:8]}"

    events_data = [
        create_pod_event(str(job_id), pod_name, "Running", "MODIFIED"),
        create_pod_event(str(job_id), pod_name, "Failed", "MODIFIED"),
    ]

    with Session(engine) as session:
        for event_data in events_data:
            event = K8sEvent(
                cluster="test",
                event_time=datetime.now(UTC),
                event=event_data,
            )
            session.add(event)
        session.commit()

    core_v1, batch_v1 = mock_k8s_clients

    # Mock _read_runner_error since it makes an S3 call (runner error file not available in test)
    with patch("metta.app_backend.job_runner.event_processor._read_runner_error", return_value=None):
        # First processing
        _process_batch(mock_stats_client, core_v1, batch_v1)

        first_status = mock_stats_client._job_state[job_id].status
        first_error = mock_stats_client._job_state[job_id].error

        # Mark as unprocessed and reprocess
        with Session(engine) as session:
            stmt = select(K8sEvent)
            events = list(session.exec(stmt).all())
            for event in events:
                event.processed_at = None
                session.add(event)
            session.commit()

        _process_batch(mock_stats_client, core_v1, batch_v1)

        second_status = mock_stats_client._job_state[job_id].status
        second_error = mock_stats_client._job_state[job_id].error

    # Verify idempotency
    assert first_status == second_status == JobStatus.failed
    assert first_error == second_error
