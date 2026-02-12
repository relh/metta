# pyright: reportArgumentType=false
# SQLModel's Relationship() returns the target type, not SQLAlchemy's InstrumentedAttribute,
# causing false positives on join() and selectinload() calls.

from typing import Any
from uuid import UUID

from sqlalchemy import func, union
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import col, select

from metta.app_backend.database import get_db, with_db
from metta.app_backend.models.policies import Policy, PolicyVersion, PolicyVersionTag
from metta.app_backend.models.tournament import Pool, PoolPlayer, Season
from metta.app_backend.tournament.settings import HIDDEN_SEASONS


def _visible_pv_ids_subquery(user_id: str | None) -> Any:
    """Return a subquery of policy_version IDs visible to the given user (or anonymous if None).

    A policy version is visible if:
    - It belongs to a policy owned by the user (if user_id is provided), OR
    - It is submitted to a non-hidden tournament season (via PoolPlayer -> Pool -> Season)
    """
    # Policy versions in non-hidden seasons
    in_public_season = (
        select(PoolPlayer.policy_version_id)
        .join(PoolPlayer.pool)
        .join(Pool.season)
        .where(col(Season.name).not_in(HIDDEN_SEASONS))
    )

    if user_id is None:
        # Anonymous user: only season-based visibility
        return in_public_season

    # Logged-in user: owner OR season-based visibility
    owned_by_user = select(PolicyVersion.id).join(Policy).where(Policy.user_id == user_id)
    return union(in_public_season, owned_by_user)


class PolicyNameTakenError(Exception):
    def __init__(self, name: str, existing_user_id: str):
        self.name = name
        self.existing_user_id = existing_user_id
        super().__init__(
            f"Policy name '{name}' is already taken by user '{existing_user_id}'. Please choose a different name."
        )


@with_db
async def upsert_policy(name: str, user_id: str, attributes: dict | None = None) -> UUID:
    session = get_db()
    existing = (await session.execute(select(Policy).filter_by(name=name))).scalar_one_or_none()

    if existing is not None:
        if existing.user_id != user_id:
            raise PolicyNameTakenError(name, existing.user_id)
        return existing.id

    policy = Policy(name=name, user_id=user_id, attributes=attributes or {})
    session.add(policy)
    await session.flush()
    return policy.id


@with_db
async def get_latest_policy_version(policy_id: UUID) -> int | None:
    session = get_db()
    result = (
        await session.execute(select(func.max(PolicyVersion.version)).filter_by(policy_id=policy_id))
    ).scalar_one_or_none()
    return result


@with_db
async def create_policy_version(
    policy_id: UUID,
    s3_path: str | None,
    git_hash: str | None,
    policy_spec: dict | None,
    attributes: dict | None,
) -> UUID:
    session = get_db()
    latest = await _get_latest_policy_version_internal(session, policy_id)
    next_version = (latest or 0) + 1

    pv = PolicyVersion(
        policy_id=policy_id,
        version=next_version,
        s3_path=s3_path,
        git_hash=git_hash,
        policy_spec=policy_spec or {},
        attributes=attributes or {},
    )
    session.add(pv)
    await session.flush()
    return pv.id


async def _get_latest_policy_version_internal(session: AsyncSession, policy_id: UUID) -> int | None:
    return (
        await session.execute(select(func.max(PolicyVersion.version)).filter_by(policy_id=policy_id))
    ).scalar_one_or_none()


@with_db
async def get_policy_version_with_name(
    policy_version_id: UUID,
    visible_to_user_id: str | None = None,
    filter_visibility: bool = False,
) -> PolicyVersion | None:
    session = get_db()
    query = (
        select(PolicyVersion)
        .filter_by(id=policy_version_id)
        .options(selectinload(PolicyVersion.policy), selectinload(PolicyVersion.tags))
    )
    if filter_visibility:
        visible_pv_ids = _visible_pv_ids_subquery(visible_to_user_id)
        query = query.where(col(PolicyVersion.id).in_(visible_pv_ids))
    return (await session.execute(query)).scalar_one_or_none()


@with_db
async def get_policies(
    name_exact: str | None = None,
    name_fuzzy: str | None = None,
    limit: int = 50,
    offset: int = 0,
    visible_to_user_id: str | None = None,
    filter_visibility: bool = False,
) -> tuple[list[Policy], int]:
    session = get_db()

    query = select(Policy)
    count_query = select(func.count()).select_from(Policy)

    if name_exact:
        query = query.filter_by(name=name_exact)
        count_query = count_query.filter_by(name=name_exact)

    if name_fuzzy:
        query = query.where(col(Policy.name).ilike(f"%{name_fuzzy}%"))
        count_query = count_query.where(col(Policy.name).ilike(f"%{name_fuzzy}%"))

    # Visibility filtering: only show policies that have at least one visible version
    if filter_visibility:
        visible_pv_ids = _visible_pv_ids_subquery(visible_to_user_id)
        has_visible_version = select(PolicyVersion.policy_id).where(col(PolicyVersion.id).in_(visible_pv_ids))

        # policies always have at least one version, so filtering for visible versions is ok
        query = query.where(col(Policy.id).in_(has_visible_version))
        count_query = count_query.where(col(Policy.id).in_(has_visible_version))

    total = (await session.execute(count_query)).scalar_one()

    policies = list(
        (
            await session.execute(
                query.order_by(col(Policy.created_at).desc())
                .limit(limit)
                .offset(offset)
                .options(selectinload(Policy.versions))
            )
        )
        .scalars()
        .all()
    )

    return policies, total


@with_db
async def get_policy_versions(
    name_exact: str | None = None,
    name_fuzzy: str | None = None,
    version: int | None = None,
    policy_version_ids: list[UUID] | None = None,
    policy_id: UUID | None = None,
    user_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    visible_to_user_id: str | None = None,
    filter_visibility: bool = False,
) -> tuple[list[PolicyVersion], int]:
    session = get_db()

    query = select(PolicyVersion).join(PolicyVersion.policy)
    count_query = select(func.count()).select_from(PolicyVersion).join(PolicyVersion.policy)

    if policy_id is not None:
        query = query.where(PolicyVersion.policy_id == policy_id)
        count_query = count_query.where(PolicyVersion.policy_id == policy_id)

    if policy_version_ids:
        query = query.where(col(PolicyVersion.id).in_(policy_version_ids))
        count_query = count_query.where(col(PolicyVersion.id).in_(policy_version_ids))

    if name_exact:
        query = query.where(Policy.name == name_exact)
        count_query = count_query.where(Policy.name == name_exact)

    if name_fuzzy:
        query = query.where(col(Policy.name).ilike(f"%{name_fuzzy}%"))
        count_query = count_query.where(col(Policy.name).ilike(f"%{name_fuzzy}%"))

    if version is not None:
        query = query.where(PolicyVersion.version == version)
        count_query = count_query.where(PolicyVersion.version == version)

    if user_id is not None:
        query = query.where(Policy.user_id == user_id)
        count_query = count_query.where(Policy.user_id == user_id)

    # Visibility filtering: only show policy versions that are visible to the user
    if filter_visibility:
        visible_pv_ids = _visible_pv_ids_subquery(visible_to_user_id)
        query = query.where(col(PolicyVersion.id).in_(visible_pv_ids))
        count_query = count_query.where(col(PolicyVersion.id).in_(visible_pv_ids))

    total = (await session.execute(count_query)).scalar_one()

    versions = list(
        (
            await session.execute(
                query.order_by(col(PolicyVersion.created_at).desc())
                .limit(limit)
                .offset(offset)
                .options(selectinload(PolicyVersion.policy), selectinload(PolicyVersion.tags))
            )
        )
        .scalars()
        .all()
    )

    return versions, total


@with_db
async def upsert_policy_version_tags(policy_version_id: UUID, tags: dict[str, str]) -> None:
    if not tags:
        return

    session = get_db()

    for key, value in tags.items():
        existing = (
            await session.execute(select(PolicyVersionTag).filter_by(policy_version_id=policy_version_id, key=key))
        ).scalar_one_or_none()

        if existing:
            existing.value = value
        else:
            session.add(PolicyVersionTag(policy_version_id=policy_version_id, key=key, value=value))

    await session.flush()
