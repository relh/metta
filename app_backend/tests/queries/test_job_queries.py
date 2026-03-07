from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from sqlmodel import Session, create_engine

from metta.app_backend.models.job_request import JobRequest, JobRequestUpdate, JobStatus, JobType
from metta.app_backend.queries.job_queries import get_job, update_job


@pytest.fixture
def engine(stats_repo):
    return create_engine(stats_repo)


def _create_job(engine, *, status: JobStatus = JobStatus.pending) -> UUID:
    job_id = uuid4()
    job = JobRequest(
        id=job_id,
        job={"type": "single_episode", "policy_uris": [], "assignments": [0], "env": {"name": "test"}},
        status=status,
        job_type=JobType.episode,
        user_id="test-user",
    )
    with Session(engine) as session:
        session.add(job)
        session.commit()
    return job_id


@patch("metta.app_backend.queries.job_queries.get_job_metrics")
class TestUpdateJobTransitions:
    def test_forward_transition_applies(self, mock_metrics, engine):
        job_id = _create_job(engine, status=JobStatus.dispatched)
        result = update_job(engine, job_id, JobRequestUpdate(status=JobStatus.running))
        assert result is not None
        assert result.status == JobStatus.running

    def test_backward_transition_rejected(self, mock_metrics, engine):
        job_id = _create_job(engine, status=JobStatus.running)
        result = update_job(engine, job_id, JobRequestUpdate(status=JobStatus.dispatched))
        assert result is not None
        assert result.status == JobStatus.running

    def test_same_status_rejected(self, mock_metrics, engine):
        job_id = _create_job(engine, status=JobStatus.running)
        result = update_job(engine, job_id, JobRequestUpdate(status=JobStatus.running))
        assert result is not None
        assert result.status == JobStatus.running

    def test_completed_blocks_all_updates(self, mock_metrics, engine):
        job_id = _create_job(engine, status=JobStatus.completed)
        result = update_job(engine, job_id, JobRequestUpdate(status=JobStatus.failed))
        assert result is not None
        assert result.status == JobStatus.completed

    def test_failed_blocks_all_updates(self, mock_metrics, engine):
        job_id = _create_job(engine, status=JobStatus.failed)
        result = update_job(engine, job_id, JobRequestUpdate(status=JobStatus.completed))
        assert result is not None
        assert result.status == JobStatus.failed

    def test_invalid_transition_rejected(self, mock_metrics, engine):
        job_id = _create_job(engine, status=JobStatus.pending)
        result = update_job(engine, job_id, JobRequestUpdate(status=JobStatus.running))
        assert result is not None
        assert result.status == JobStatus.pending

    def test_dispatched_to_failed_allowed(self, mock_metrics, engine):
        job_id = _create_job(engine, status=JobStatus.dispatched)
        result = update_job(engine, job_id, JobRequestUpdate(status=JobStatus.failed, error="pod died"))
        assert result is not None
        assert result.status == JobStatus.failed
        assert result.error == "pod died"

    def test_missing_job_returns_none(self, mock_metrics, engine):
        result = update_job(engine, uuid4(), JobRequestUpdate(status=JobStatus.running))
        assert result is None

    def test_non_status_fields_update_without_status_change(self, mock_metrics, engine):
        job_id = _create_job(engine, status=JobStatus.running)
        result = update_job(engine, job_id, JobRequestUpdate(worker="pod-abc"))
        assert result is not None
        assert result.worker == "pod-abc"
        assert result.status == JobStatus.running


class TestGetJob:
    def test_returns_job(self, engine):
        job_id = _create_job(engine)
        result = get_job(engine, job_id)
        assert result is not None
        assert result.id == job_id

    def test_returns_none_for_missing(self, engine):
        assert get_job(engine, uuid4()) is None
