from uuid import UUID

from metta.app_backend.tournament.commissioners.base import CommissionerBase
from metta.app_backend.tournament.commissioners.teams.base import TeamCommissionerBase
from metta.app_backend.tournament.registry import SEASONS


async def initialize_commissioner(commissioner: CommissionerBase) -> CommissionerBase:
    if isinstance(commissioner, TeamCommissionerBase):
        await commissioner._load_config()
    return commissioner


async def build_commissioner(season_name: str, *, season_id: UUID) -> CommissionerBase:
    commissioner_cls = SEASONS[season_name]
    return await initialize_commissioner(commissioner_cls(season_id=season_id))
