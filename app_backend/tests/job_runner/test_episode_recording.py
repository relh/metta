from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlmodel import Session, create_engine, select

from metta.app_backend.job_runner.episode_recording import EpisodeJobSummary, record_job_episode
from metta.app_backend.models.episodes import EpisodeJob, EpisodePolicy
from metta.app_backend.models.job_request import JobPolicyVersion, JobRequest, JobStatus, JobType
from metta.app_backend.models.policies import Policy, PolicyVersion
from mettagrid.runner.types import PureSingleEpisodeResult


@pytest.fixture
def engine(stats_repo: str):
    return create_engine(stats_repo)


def _create_job_with_policy_versions(
    engine,
    *,
    policy_uris: list[str],
    stored_positions: list[int],
) -> tuple[UUID, dict[int, UUID]]:
    job_id = uuid4()

    with Session(engine) as session:
        policy_a = Policy(name=f"policy-a-{uuid4()}", user_id="test-user")
        policy_b = Policy(name=f"policy-b-{uuid4()}", user_id="test-user")
        session.add(policy_a)
        session.add(policy_b)
        session.flush()

        pv_a = PolicyVersion(policy_id=policy_a.id, version=1)
        pv_b = PolicyVersion(policy_id=policy_b.id, version=1)
        session.add(pv_a)
        session.add(pv_b)
        session.flush()

        job = JobRequest(
            id=job_id,
            job={"policy_uris": policy_uris, "assignments": [0, 1]},
            status=JobStatus.running,
            job_type=JobType.episode,
            user_id="test-user",
        )
        session.add(job)
        session.flush()

        policy_version_ids = {0: pv_a.id, 1: pv_b.id}
        for position in stored_positions:
            session.add(
                JobPolicyVersion(
                    job_id=job_id,
                    position=position,
                    policy_version_id=policy_version_ids[position],
                )
            )

        session.commit()

    return job_id, policy_version_ids


def _results() -> PureSingleEpisodeResult:
    return PureSingleEpisodeResult(
        rewards=[1.0, 2.0],
        action_timeouts=[0, 0],
        stats={"game": {}, "agent": [{}, {}]},
        steps=5,
    )


def test_record_job_episode_uses_persisted_job_policy_versions(engine) -> None:
    job_id, policy_version_ids = _create_job_with_policy_versions(
        engine,
        policy_uris=["metta://policy/not-a-real-policy", "metta://policy/still-not-real"],
        stored_positions=[0, 1],
    )
    job = EpisodeJobSummary.model_validate(
        {
            "policy_uris": ["metta://policy/not-a-real-policy", "metta://policy/still-not-real"],
            "assignments": [0, 1],
        }
    )

    with patch("metta.app_backend.job_runner.episode_recording.get_job_metrics") as mock_metrics:
        mock_metrics.return_value = MagicMock()
        episode_id = record_job_episode(job_id, job, _results(), engine)

    with Session(engine) as session:
        episode_job = session.exec(select(EpisodeJob).where(EpisodeJob.job_id == job_id)).one()
        episode_policies = session.exec(select(EpisodePolicy).where(EpisodePolicy.episode_id == episode_id)).all()
        stored_job = session.get(JobRequest, job_id)

    assert episode_job.episode_id == episode_id
    assert {row.policy_version_id for row in episode_policies} == set(policy_version_ids.values())
    assert stored_job is not None
    assert stored_job.result == {"episode_id": str(episode_id)}


def test_record_job_episode_fails_on_incomplete_job_policy_versions(engine) -> None:
    job_id, _ = _create_job_with_policy_versions(
        engine,
        policy_uris=["metta://policy/a", "metta://policy/b"],
        stored_positions=[0],
    )
    job = EpisodeJobSummary.model_validate(
        {
            "policy_uris": ["metta://policy/a", "metta://policy/b"],
            "assignments": [0, 1],
        }
    )

    with pytest.raises(ValueError, match="stored policy versions for 2 policy URIs"):
        record_job_episode(job_id, job, _results(), engine)

    with Session(engine) as session:
        episode_jobs = session.exec(select(EpisodeJob).where(EpisodeJob.job_id == job_id)).all()

    assert episode_jobs == []
