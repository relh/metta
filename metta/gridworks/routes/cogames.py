from fastapi import APIRouter, HTTPException

from cogames.cli.mission import get_all_missions_list as _get_missions
from cogames.core import CoGameMission
from cogames.core import CoGameMissionVariant as MissionVariant
from cogames.games.cogs_vs_clips.game import VARIANTS
from cogames.games.cogs_vs_clips.train.cvc_curriculum import split_variants
from metta.gridworks.common import ConfigWithExtraInfo, extend_config
from mettagrid.mapgen.utils.storable_map import StorableMap, StorableMapDict


def _get_mission(mission_name: str, variants: str = "") -> CoGameMission:
    mission = next((mission for mission in _get_missions() if mission.name == mission_name), None)
    if mission is None:
        raise HTTPException(status_code=404, detail=f"Mission {mission_name} not found")

    variant_names = [v for v in variants.split(",") if v]
    try:
        parsed_variants, reward_variants = split_variants(variant_names)
        if reward_variants:
            reward_list = ", ".join(reward_variants)
            raise ValueError(f"Reward variants are not supported in this context: {reward_list}")
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return mission.with_variants(parsed_variants)


def make_cogames_routes() -> APIRouter:
    router = APIRouter(prefix="/cogames")

    @router.get("/missions")
    def get_missions() -> list[ConfigWithExtraInfo]:
        return [extend_config(mission) for mission in _get_missions()]

    @router.get("/missions/{mission_name}")
    def get_mission(mission_name: str, variants: str = "") -> ConfigWithExtraInfo:
        mission = _get_mission(mission_name, variants)
        return extend_config(mission)

    @router.get("/missions/{mission_name}/map")
    def get_mission_map(mission_name: str, variants: str = "") -> StorableMapDict:
        mission = _get_mission(mission_name, variants)
        env = mission.make_env()
        return StorableMap.from_cfg(env.game.map_builder).to_dict()

    @router.get("/missions/{mission_name}/env")
    def get_mission_env(mission_name: str, variants: str = "") -> ConfigWithExtraInfo:
        mission = _get_mission(mission_name, variants)
        env = mission.make_env()
        return extend_config(env)

    @router.get("/variants")
    def get_variants() -> list[MissionVariant]:
        return VARIANTS

    return router
