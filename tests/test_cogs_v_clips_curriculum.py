import pytest

from recipes.experiment.cogs_v_clips import DEFAULT_CURRICULUM_MISSIONS, _resolve_mission_template


class TestCurriculumMissions:
    @pytest.mark.parametrize("mission_name", DEFAULT_CURRICULUM_MISSIONS)
    def test_curriculum_mission_exists(self, mission_name: str):
        mission = _resolve_mission_template(mission_name)
        assert mission is not None
        assert mission.name or mission.full_name()
