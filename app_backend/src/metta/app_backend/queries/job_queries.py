import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from metta.app_backend.models.episodes import (
    Episode,
    EpisodeAgentMetric,
    EpisodeJob,
    EpisodePolicy,
    EpisodePolicyMetric,
    EpisodeTag,
)
from metta.app_backend.models.job_request import JobRequest, JobRequestUpdate, JobStatus
from metta.app_backend.models.policies import Policy, PolicyVersion
from metta.app_backend.otel.job_metrics import get_job_metrics
from metta.app_backend.queries.episode_metrics import (
    aggregate_policy_agent_counts,
    aggregate_policy_metrics,
    filter_agent_metrics,
)

logger = logging.getLogger(__name__)

_STATUS_ORDER: dict[JobStatus, int] = {
    JobStatus.pending: 0,
    JobStatus.dispatched: 1,
    JobStatus.running: 2,
    JobStatus.completed: 3,
    JobStatus.failed: 3,
}

VALID_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.pending: {JobStatus.dispatched},
    JobStatus.dispatched: {JobStatus.running, JobStatus.failed, JobStatus.completed},
    JobStatus.running: {JobStatus.completed, JobStatus.failed},
}


def get_job(engine: Engine, job_id: UUID) -> JobRequest | None:
    with Session(engine) as session:
        return session.get(JobRequest, job_id)


def update_job(engine: Engine, job_id: UUID, update: JobRequestUpdate) -> JobRequest | None:
    with Session(engine) as session:
        job = session.get(JobRequest, job_id)
        if job is None:
            return None

        previous_status = job.status
        status_changed = False

        if update.status is not None:
            if _STATUS_ORDER[update.status] <= _STATUS_ORDER[job.status]:
                return job
            allowed = VALID_TRANSITIONS.get(job.status, set())
            if update.status not in allowed:
                return job
            job.status = update.status
            status_changed = True

        if update.running_at is not None:
            job.running_at = update.running_at
        if update.completed_at is not None:
            job.completed_at = update.completed_at
        if update.worker is not None:
            job.worker = update.worker
        if update.error is not None:
            job.error = update.error
        if update.error_type is not None:
            job.error_type = update.error_type
        if update.result is not None:
            job.result = update.result

        if status_changed:
            assert update.status is not None
            transition_time = update.completed_at or update.running_at or datetime.now(UTC)
            metrics = get_job_metrics()
            result_data = job.result or {}
            raw_cost = result_data.get("cost_usd")
            stored_cost = raw_cost if isinstance(raw_cost, (int, float)) and not isinstance(raw_cost, bool) else None
            metrics.record_transition(
                previous_status,
                update.status,
                job,
                transition_time,
                job.error_type,
                cost_usd=stored_cost,
            )

        session.commit()
        session.refresh(job)
        return job


def list_jobs_by_status(engine: Engine, statuses: list[JobStatus], limit: int = 1000) -> list[JobRequest]:
    with Session(engine) as session:
        stmt = select(JobRequest).where(col(JobRequest.status).in_(statuses)).limit(limit)
        return list(session.exec(stmt).all())


def resolve_policy_version_id(engine: Engine, uri: str) -> UUID | None:
    if not uri.startswith("metta://"):
        return None
    path = uri[len("metta://") :]
    parts = path.split("/")
    if len(parts) < 2 or parts[0] != "policy":
        return None
    identifier = parts[1]

    with Session(engine) as session:
        try:
            pv_id = UUID(identifier)
            pv = session.get(PolicyVersion, pv_id)
            return pv.id if pv else None
        except ValueError:
            pass

        if identifier.endswith(":latest"):
            name = identifier[:-7]
            version = None
        elif ":" in identifier:
            name, version_str = identifier.rsplit(":", 1)
            version_str = version_str.lstrip("v")
            version = int(version_str) if version_str.isdigit() else None
        else:
            name = identifier
            version = None

        stmt = select(PolicyVersion).join(Policy).where(Policy.name == name)
        if version is not None:
            stmt = stmt.where(PolicyVersion.version == version)
        else:
            stmt = stmt.order_by(PolicyVersion.version.desc())  # type: ignore[union-attr]
        stmt = stmt.limit(1)
        pv = session.exec(stmt).first()
        return pv.id if pv else None


def _policy_uuid_to_internal_id(session: Session, pv_uuids: list[UUID]) -> dict[UUID, int]:
    if not pv_uuids:
        return {}
    stmt = select(PolicyVersion.id, PolicyVersion.internal_id).where(col(PolicyVersion.id).in_(pv_uuids))
    rows = session.exec(stmt).all()
    return {row[0]: row[1] for row in rows if row[1] is not None}


def record_episode_direct(
    engine: Engine,
    *,
    episode_id: UUID,
    job_id: UUID,
    episode_tags: dict[str, str],
    policy_version_ids: list[UUID | None],
    replay_uri: str | None,
    assignments: list[int],
    agent_metrics: list[tuple[int, str, float]],
) -> None:
    agent_policy_map: dict[int, UUID] = {}
    for agent_id, assignment in enumerate(assignments):
        pv_id = policy_version_ids[assignment]
        if pv_id:
            agent_policy_map[agent_id] = pv_id

    filtered = filter_agent_metrics(agent_metrics)
    policy_agent_counts = aggregate_policy_agent_counts(agent_policy_map)
    policy_metrics = aggregate_policy_metrics(filtered, agent_policy_map)

    with Session(engine) as session:
        episode = Episode(id=episode_id, data_uri="", replay_url=replay_uri)
        session.add(episode)
        session.flush()
        session.refresh(episode, attribute_names=["internal_id"])
        assert episode.internal_id is not None

        for pv_id, count in policy_agent_counts.items():
            session.add(EpisodePolicy(episode_id=episode_id, policy_version_id=pv_id, num_agents=count))

        for key, value in episode_tags.items():
            session.add(EpisodeTag(episode_id=episode_id, key=key, value=value))

        session.flush()

        pv_uuid_to_internal = _policy_uuid_to_internal_id(session, list(policy_agent_counts.keys()))

        for pv_id, metrics in policy_metrics.items():
            if pv_id not in pv_uuid_to_internal:
                continue
            pv_internal = pv_uuid_to_internal[pv_id]
            for metric_name, value in metrics.items():
                session.add(
                    EpisodePolicyMetric(
                        episode_internal_id=episode.internal_id,
                        pv_internal_id=pv_internal,
                        metric_name=metric_name,
                        value=value,
                    )
                )

        for agent_id, metric_name, metric_value in filtered:
            if agent_id not in agent_policy_map:
                continue
            pv_id = agent_policy_map[agent_id]
            if pv_id not in pv_uuid_to_internal:
                continue
            session.add(
                EpisodeAgentMetric(
                    episode_internal_id=episode.internal_id,
                    pv_internal_id=pv_uuid_to_internal[pv_id],
                    agent_id=agent_id,
                    metric_name=metric_name,
                    value=metric_value,
                )
            )

        session.add(EpisodeJob(episode_id=episode_id, job_id=job_id))
        session.flush()
        session.commit()
