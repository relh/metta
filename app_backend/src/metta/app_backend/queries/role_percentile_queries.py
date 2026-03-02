from __future__ import annotations

# pyright: reportArgumentType=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportOptionalMemberAccess=false
# pyright: reportCallIssue=false
# SQLAlchemy typing for complex selects is noisy; keep this module readable.
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select

from metta.app_backend.database import get_db, with_db
from metta.app_backend.models.episodes import Episode, EpisodeAgentMetric, EpisodeJob
from metta.app_backend.models.policies import Policy, PolicyVersion
from metta.app_backend.models.tournament import Match, MatchStatus


@dataclass(frozen=True)
class RoleMetric:
    key: str
    source_names: tuple[str, ...]
    higher_is_better: bool
    include_in_overall: bool = True


@dataclass(frozen=True)
class RoleLeaderboardRow:
    rank: int
    policy_version_id: UUID
    policy_name: str
    policy_version: int
    percentile: float
    details: dict[str, Any]
    updated_at: datetime


@dataclass(frozen=True)
class RolePercentileRow:
    role: str
    percentile: float
    details: dict[str, Any]
    updated_at: datetime


DEATH_SOURCE_NAMES = ("death",)
REWARD_SOURCE_NAMES = ("reward",)

ROLE_METRICS: dict[str, list[RoleMetric]] = {
    "miner": [
        RoleMetric("miner.gained", ("miner.gained",), higher_is_better=True),
        RoleMetric("reward", REWARD_SOURCE_NAMES, higher_is_better=True, include_in_overall=False),
        RoleMetric("germanium.deposited", ("germanium.deposited", "germanium.lost"), higher_is_better=True),
        RoleMetric("silicon.deposited", ("silicon.deposited", "silicon.lost"), higher_is_better=True),
        RoleMetric("carbon.deposited", ("carbon.deposited", "carbon.lost"), higher_is_better=True),
        RoleMetric("oxygen.deposited", ("oxygen.deposited", "oxygen.lost"), higher_is_better=True),
        RoleMetric("heart.gained", ("heart.gained",), higher_is_better=False),
        RoleMetric("scout.gained", ("scout.gained",), higher_is_better=False),
        RoleMetric("scrambler.gained", ("scrambler.gained",), higher_is_better=False),
        RoleMetric("aligner.gained", ("aligner.gained",), higher_is_better=False),
        RoleMetric("death", DEATH_SOURCE_NAMES, higher_is_better=False),
    ],
    "scout": [
        RoleMetric("scout.gained", ("scout.gained",), higher_is_better=True),
        RoleMetric("reward", REWARD_SOURCE_NAMES, higher_is_better=True, include_in_overall=False),
        RoleMetric("cell.visited", ("cell.visited",), higher_is_better=True),
        RoleMetric("miner.gained", ("miner.gained",), higher_is_better=False),
        RoleMetric("scrambler.gained", ("scrambler.gained",), higher_is_better=False),
        RoleMetric("aligner.gained", ("aligner.gained",), higher_is_better=False),
        RoleMetric("death", DEATH_SOURCE_NAMES, higher_is_better=False),
    ],
    "scrambler": [
        RoleMetric("scrambler.gained", ("scrambler.gained",), higher_is_better=True),
        RoleMetric("reward", REWARD_SOURCE_NAMES, higher_is_better=True, include_in_overall=False),
        RoleMetric(
            "junction.scrambled",
            ("junction.scrambled_by_agent", "junction.scrambled"),
            higher_is_better=True,
        ),
        RoleMetric("heart.gained", ("heart.gained",), higher_is_better=True),
        RoleMetric("miner.gained", ("miner.gained",), higher_is_better=False),
        RoleMetric("scout.gained", ("scout.gained",), higher_is_better=False),
        RoleMetric("aligner.gained", ("aligner.gained",), higher_is_better=False),
        RoleMetric("death", DEATH_SOURCE_NAMES, higher_is_better=False),
    ],
    "aligner": [
        RoleMetric("aligner.gained", ("aligner.gained",), higher_is_better=True),
        RoleMetric("reward", REWARD_SOURCE_NAMES, higher_is_better=True, include_in_overall=False),
        RoleMetric(
            "junction.aligned",
            ("junction.aligned_by_agent", "junction.aligned"),
            higher_is_better=True,
        ),
        RoleMetric("heart.gained", ("heart.gained",), higher_is_better=True),
        RoleMetric("miner.gained", ("miner.gained",), higher_is_better=False),
        RoleMetric("scout.gained", ("scout.gained",), higher_is_better=False),
        RoleMetric("scrambler.gained", ("scrambler.gained",), higher_is_better=False),
        RoleMetric("death", DEATH_SOURCE_NAMES, higher_is_better=False),
    ],
}


def _validate_role_metrics(role_metrics: dict[str, list[RoleMetric]]) -> None:
    for role, metrics in role_metrics.items():
        for metric in metrics:
            if len(metric.source_names) == 0:
                raise ValueError(f"Role metric {role}.{metric.key} must declare at least one source metric name")
            if len(set(metric.source_names)) != len(metric.source_names):
                raise ValueError(f"Role metric {role}.{metric.key} has duplicate source metric names")


_validate_role_metrics(ROLE_METRICS)


def _percentile_rank(value: float, values: list[float], higher_is_better: bool) -> float:
    n = len(values)
    if n <= 1:
        return 100.0
    if higher_is_better:
        better = sum(1 for other_value in values if other_value > value)
    else:
        better = sum(1 for other_value in values if other_value < value)
    return (1.0 - (better / (n - 1))) * 100.0


def _pool_episode_internal_ids(pool_id: UUID):
    return (
        select(Episode.internal_id.label("episode_internal_id"))
        .join(EpisodeJob, EpisodeJob.episode_id == Episode.id)
        .join(Match, Match.job_id == EpisodeJob.job_id)
        .where(Match.pool_id == pool_id, Match.status == MatchStatus.completed)
        .distinct()
        .subquery("pool_episodes")
    )


async def _metric_percentiles(
    pool_id: UUID,
    metric: RoleMetric,
) -> list[dict[str, Any]]:
    session = get_db()
    pool_episodes = _pool_episode_internal_ids(pool_id)
    stmt = (
        select(
            PolicyVersion.id.label("policy_version_id"),
            EpisodeAgentMetric.metric_name.label("metric_name"),
            func.avg(EpisodeAgentMetric.value).label("avg_value"),
            func.count().label("sample_count"),
        )
        .select_from(EpisodeAgentMetric)
        .join(pool_episodes, pool_episodes.c.episode_internal_id == EpisodeAgentMetric.episode_internal_id)
        .join(PolicyVersion, PolicyVersion.internal_id == EpisodeAgentMetric.pv_internal_id)
        .where(EpisodeAgentMetric.metric_name.in_(metric.source_names))
        .group_by(PolicyVersion.id, EpisodeAgentMetric.metric_name)
    )
    rows = (await session.execute(stmt)).mappings().all()
    if not rows:
        # If the metric is absent for the entire pool, it should not affect role scoring.
        return []

    by_policy: dict[UUID, dict[str, Any]] = {}
    for row in rows:
        pv_id = row["policy_version_id"]
        source_name = str(row["metric_name"])
        avg_value = float(row["avg_value"])
        sample_count = int(row["sample_count"])

        policy_bucket = by_policy.setdefault(
            pv_id,
            {
                "source_metrics": {},
            },
        )
        policy_bucket["source_metrics"][source_name] = {
            "avg": avg_value,
            "samples": sample_count,
        }

    selected_source_by_policy: dict[UUID, tuple[float, int]] = {}
    for pv_id, data in by_policy.items():
        source_metrics = data["source_metrics"]
        selected_source = next((source for source in metric.source_names if source in source_metrics), None)
        if selected_source is None:
            continue
        selected_avg = float(source_metrics[selected_source]["avg"])
        selected_samples = int(source_metrics[selected_source]["samples"])
        if selected_samples <= 0:
            continue
        selected_source_by_policy[pv_id] = (selected_avg, selected_samples)

    values = {pv_id: avg for pv_id, (avg, _samples) in selected_source_by_policy.items()}
    all_values = list(values.values())
    results: list[dict[str, Any]] = []
    for pv_id, value in values.items():
        sample_count = int(selected_source_by_policy[pv_id][1])
        percentile = _percentile_rank(value, all_values, metric.higher_is_better)

        results.append(
            {
                "policy_version_id": pv_id,
                "avg_value": float(value),
                "sample_count": sample_count,
                "percentile": float(percentile),
                "source_metrics": by_policy[pv_id]["source_metrics"],
            }
        )
    return results


async def _compute_role_percentile_payloads(
    pool_id: UUID,
    roles: tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    selected_roles = roles if roles is not None else tuple(ROLE_METRICS)
    unknown_roles = [role for role in selected_roles if role not in ROLE_METRICS]
    if unknown_roles:
        unknown_csv = ", ".join(sorted(unknown_roles))
        raise ValueError(f"Unknown role(s) requested: {unknown_csv}")

    role_payloads: dict[tuple[UUID, str], dict[str, Any]] = {}

    for role in selected_roles:
        metrics = ROLE_METRICS[role]
        for metric in metrics:
            rows = await _metric_percentiles(pool_id, metric)
            for row in rows:
                pv_id = row["policy_version_id"]
                key = (pv_id, role)
                payload = role_payloads.setdefault(
                    key,
                    {
                        "metrics": {},
                        "percentile_sum": 0.0,
                        "percentile_count": 0,
                    },
                )
                percentile = float(row["percentile"])

                payload["metrics"][metric.key] = {
                    "avg": float(row["avg_value"]),
                    "percentile": percentile,
                    "higher_is_better": metric.higher_is_better,
                    "include_in_overall": metric.include_in_overall,
                    "samples": int(row["sample_count"]),
                    "source_names": list(metric.source_names),
                    "source_metrics": row["source_metrics"],
                }
                if metric.include_in_overall:
                    payload["percentile_sum"] += percentile
                    payload["percentile_count"] += 1

    role_rows: list[dict[str, Any]] = []
    for (pv_id, role), payload in role_payloads.items():
        score_count = int(payload["percentile_count"])
        if score_count <= 0:
            continue
        overall = float(payload["percentile_sum"]) / float(score_count)
        role_rows.append(
            {
                "policy_version_id": pv_id,
                "role": role,
                "percentile": overall,
                "details": {
                    "metrics": payload["metrics"],
                    "overall_percentile": overall,
                },
            }
        )

    return role_rows


@with_db
async def compute_policy_role_percentiles(pool_id: UUID, policy_version_id: UUID) -> list[RolePercentileRow]:
    rows = await _compute_role_percentile_payloads(pool_id)
    computed_at = datetime.now()
    matching = [row for row in rows if row["policy_version_id"] == policy_version_id]
    matching.sort(key=lambda row: str(row["role"]))
    return [
        RolePercentileRow(
            role=str(row["role"]),
            percentile=float(row["percentile"]),
            details=row["details"],
            updated_at=computed_at,
        )
        for row in matching
    ]


@with_db
async def compute_role_leaderboard(pool_id: UUID, role: str, limit: int = 100) -> list[RoleLeaderboardRow]:
    if role not in ROLE_METRICS:
        return []

    session = get_db()
    role_rows = await _compute_role_percentile_payloads(pool_id, roles=(role,))
    if not role_rows:
        return []

    role_rows.sort(
        key=lambda row: (
            -float(row["percentile"]),
            str(row["policy_version_id"]),
        )
    )

    selected_rows = role_rows[:limit]
    selected_policy_ids = [row["policy_version_id"] for row in selected_rows]
    info_stmt = (
        select(PolicyVersion.id, Policy.name, PolicyVersion.version)
        .join(Policy, Policy.id == PolicyVersion.policy_id)
        .where(PolicyVersion.id.in_(selected_policy_ids))
    )
    info_rows = (await session.execute(info_stmt)).all()
    policy_info: dict[UUID, tuple[str, int]] = {row[0]: (str(row[1]), int(row[2])) for row in info_rows}
    computed_at = datetime.now()
    results: list[RoleLeaderboardRow] = []
    for idx, row in enumerate(selected_rows):
        pv_id = row["policy_version_id"]
        info = policy_info.get(pv_id)
        if info is None:
            raise AssertionError(f"Missing policy info for selected policy version {pv_id}")
        policy_name, policy_version = info
        results.append(
            RoleLeaderboardRow(
                rank=idx + 1,
                policy_version_id=pv_id,
                policy_name=policy_name,
                policy_version=policy_version,
                percentile=float(row["percentile"]),
                details=row["details"],
                updated_at=computed_at,
            )
        )
    return results
