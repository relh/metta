# pyright: reportArgumentType=false
# pyright: reportCallIssue=false
# pyright: reportAttributeAccessIssue=false

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import func, select, update

from metta.app_backend.database import get_db, with_db
from metta.app_backend.models.sweep import Sweep


class SweepRow(BaseModel):
    id: UUID
    name: str
    project: str
    entity: str
    wandb_sweep_id: str
    state: str
    run_counter: int
    user_id: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, sweep: Sweep) -> "SweepRow":
        return cls(
            id=sweep.id,
            name=sweep.name,
            project=sweep.project,
            entity=sweep.entity,
            wandb_sweep_id=sweep.wandb_sweep_id,
            state=sweep.state,
            run_counter=sweep.run_counter,
            user_id=sweep.user_id,
            created_at=sweep.created_at,
            updated_at=sweep.updated_at,
        )


@with_db
async def create_sweep(name: str, project: str, entity: str, wandb_sweep_id: str, user_id: str) -> UUID:
    session = get_db()
    sweep = Sweep(
        name=name,
        project=project,
        entity=entity,
        wandb_sweep_id=wandb_sweep_id,
        user_id=user_id,
    )
    session.add(sweep)
    await session.flush()
    return sweep.id


@with_db
async def get_sweep_by_name(name: str) -> Sweep | None:
    session = get_db()
    return (await session.execute(select(Sweep).filter_by(name=name))).scalar_one_or_none()


@with_db
async def get_next_sweep_run_counter(sweep_id: UUID) -> int:
    session = get_db()
    stmt = (
        update(Sweep)
        .where(Sweep.id == sweep_id)
        .values(run_counter=Sweep.run_counter + 1, updated_at=func.now())
        .returning(Sweep.run_counter)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        raise ValueError(f"Sweep {sweep_id} not found")
    return row[0]
