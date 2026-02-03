# pyright: reportArgumentType=false
# pyright: reportCallIssue=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportOptionalMemberAccess=false
# SQLModel typing causes false positives on ORM expressions in this file.

import json
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import String, cast, exists, func, literal, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import aliased

from metta.app_backend.database import get_db, with_db
from metta.app_backend.models.episodes import Episode, EpisodeJob, EpisodePolicy, EpisodePolicyMetric, EpisodeTag
from metta.app_backend.models.policies import PolicyVersion


class EpisodeWithTags(BaseModel):
    id: UUID
    primary_pv_id: UUID | None
    replay_url: str | None
    thumbnail_url: str | None
    attributes: dict[str, Any] = Field(default_factory=dict)
    eval_task_id: UUID | None
    created_at: Any
    tags: dict[str, str] = Field(default_factory=dict)
    avg_rewards: dict[UUID, float] = Field(default_factory=dict)
    job_id: UUID | None = None

    @field_validator("attributes", mode="before")
    @classmethod
    def _ensure_dict_attributes(cls, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            parsed = json.loads(value)
            if not isinstance(parsed, dict):
                raise ValueError("attributes must be a JSON object")
            return parsed
        raise ValueError("attributes must be a dictionary")


@with_db
async def record_episode(
    id: UUID,
    data_uri: str,
    primary_pv_id: UUID | None,
    replay_url: str | None,
    attributes: dict[str, Any],
    eval_task_id: UUID | None,
    thumbnail_url: str | None,
    tags: list[tuple[str, str]],
    policy_versions: list[tuple[UUID, int]],
    policy_metrics: list[tuple[UUID, str, float]],
) -> UUID:
    session = get_db()

    episode = Episode(
        id=id,
        data_uri=data_uri,
        primary_pv_id=primary_pv_id,
        replay_url=replay_url,
        thumbnail_url=thumbnail_url,
        attributes=attributes,
        eval_task_id=eval_task_id,
    )
    session.add(episode)
    await session.flush()
    await session.refresh(episode, attribute_names=["internal_id"])
    if episode.internal_id is None:
        raise RuntimeError("Episode internal_id not set after insert")

    for pv_id, num_agents in policy_versions:
        ep = EpisodePolicy(episode_id=id, policy_version_id=pv_id, num_agents=num_agents)
        session.add(ep)

    for key, value in tags:
        tag = EpisodeTag(episode_id=id, key=key, value=value)
        session.add(tag)

    await session.flush()

    if policy_metrics:
        pv_uuids = list({pv_id for pv_id, _, _ in policy_metrics})
        stmt = select(PolicyVersion.id, PolicyVersion.internal_id).where(PolicyVersion.id.in_(pv_uuids))
        pv_rows = (await session.execute(stmt)).all()
        pv_uuid_to_internal: dict[UUID, int] = {row[0]: row[1] for row in pv_rows if row[1] is not None}
        missing_pv_ids = [pv_id for pv_id in pv_uuids if pv_id not in pv_uuid_to_internal]
        if missing_pv_ids:
            missing_str = ", ".join(str(pv_id) for pv_id in missing_pv_ids)
            raise ValueError(f"Missing policy_versions.internal_id for policy_version IDs: {missing_str}")

        for pv_id, metric_name, metric_value in policy_metrics:
            metric = EpisodePolicyMetric(
                episode_internal_id=episode.internal_id,
                pv_internal_id=pv_uuid_to_internal[pv_id],
                metric_name=metric_name,
                value=metric_value,
            )
            session.add(metric)

    await session.flush()
    return id


@with_db
async def link_episode_job(episode_id: UUID, job_id: UUID) -> None:
    session = get_db()
    session.add(EpisodeJob(episode_id=episode_id, job_id=job_id))
    await session.flush()


@with_db
async def get_episodes(
    *,
    primary_policy_version_ids: list[UUID] | None = None,
    episode_ids: list[UUID] | None = None,
    tag_filters: dict[str, list[str] | None] | None = None,
    limit: int | None = 200,
    offset: int = 0,
) -> list[EpisodeWithTags]:
    session = get_db()

    tags_cte = (
        select(
            EpisodeTag.episode_id,
            func.jsonb_object_agg(EpisodeTag.key, EpisodeTag.value).label("tags"),
        )
        .group_by(EpisodeTag.episode_id)
        .cte("episode_tags_agg")
    )

    episode_alias = aliased(Episode)
    avg_rewards_cte = (
        select(
            episode_alias.id.label("episode_id"),
            func.jsonb_object_agg(
                cast(PolicyVersion.id, String),
                EpisodePolicyMetric.value / func.nullif(EpisodePolicy.num_agents, 0),
            )
            .filter(
                (EpisodePolicyMetric.metric_name == "reward")
                & EpisodePolicy.num_agents.is_not(None)
                & (EpisodePolicy.num_agents > 0)
            )
            .label("avg_rewards"),
        )
        .select_from(episode_alias)
        .join(EpisodePolicy, EpisodePolicy.episode_id == episode_alias.id)
        .join(PolicyVersion, PolicyVersion.id == EpisodePolicy.policy_version_id)
        .join(
            EpisodePolicyMetric,
            (EpisodePolicyMetric.episode_internal_id == episode_alias.internal_id)
            & (EpisodePolicyMetric.pv_internal_id == PolicyVersion.internal_id),
        )
        .group_by(episode_alias.id)
        .cte("episode_avg_rewards")
    )

    job_cte = (
        select(
            EpisodeJob.episode_id,
            func.min(cast(EpisodeJob.job_id, String)).label("job_id"),
        )
        .group_by(EpisodeJob.episode_id)
        .cte("episode_job_agg")
    )

    attributes_expr = func.coalesce(Episode.attributes, cast(literal("{}"), JSONB)).label("attributes")
    tags_expr = func.coalesce(tags_cte.c.tags, cast(literal("{}"), JSONB)).label("tags")
    avg_rewards_expr = func.coalesce(avg_rewards_cte.c.avg_rewards, cast(literal("{}"), JSONB)).label("avg_rewards")

    stmt = (
        select(
            Episode.id,
            Episode.primary_pv_id,
            Episode.replay_url,
            Episode.thumbnail_url,
            attributes_expr,
            Episode.eval_task_id,
            Episode.created_at,
            tags_expr,
            avg_rewards_expr,
            job_cte.c.job_id.label("job_id"),
        )
        .select_from(Episode)
        .outerjoin(tags_cte, tags_cte.c.episode_id == Episode.id)
        .outerjoin(avg_rewards_cte, avg_rewards_cte.c.episode_id == Episode.id)
        .outerjoin(job_cte, job_cte.c.episode_id == Episode.id)
    )

    where_conditions = []

    if primary_policy_version_ids:
        where_conditions.append(
            exists(
                select(1)
                .select_from(EpisodePolicy)
                .where(
                    EpisodePolicy.episode_id == Episode.id,
                    EpisodePolicy.policy_version_id.in_(primary_policy_version_ids),
                )
            )
        )

    if episode_ids:
        where_conditions.append(Episode.id.in_(episode_ids))

    if tag_filters:
        for tag_key, tag_values in tag_filters.items():
            tag_query = (
                select(1)
                .select_from(EpisodeTag)
                .where(
                    EpisodeTag.episode_id == Episode.id,
                    EpisodeTag.key == tag_key,
                )
            )
            if tag_values:
                tag_query = tag_query.where(EpisodeTag.value.in_(tag_values))
            where_conditions.append(exists(tag_query))

    if where_conditions:
        stmt = stmt.where(*where_conditions)

    stmt = stmt.order_by(Episode.created_at.desc())

    if limit is not None:
        stmt = stmt.limit(limit)
    if offset > 0:
        stmt = stmt.offset(offset)

    rows = (await session.execute(stmt)).mappings().all()

    episodes = []
    for row in rows:
        avg_rewards = row["avg_rewards"] or {}
        data = dict(row)
        data["tags"] = data["tags"] or {}
        data["avg_rewards"] = {UUID(str(k)): v for k, v in avg_rewards.items()}
        raw_job_id = data.get("job_id")
        try:
            data["job_id"] = UUID(raw_job_id) if raw_job_id else None
        except (ValueError, AttributeError):
            data["job_id"] = None
        episodes.append(EpisodeWithTags.model_validate(data))

    return episodes
