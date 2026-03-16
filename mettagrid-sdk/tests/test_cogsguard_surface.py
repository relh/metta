from __future__ import annotations

from mettagrid_sdk.games.cogsguard import CogsguardSemanticSurface
from mettagrid_sdk.games.cogsguard.prompt_adapter import CogsguardPromptAdapter
from mettagrid_sdk.sdk import (
    ActionCatalog,
    ActionDescriptor,
    LogRecord,
    MemoryQuery,
    MemoryRecord,
    RetrievedMemoryRecord,
    TeamSummary,
)


class _MemoryStub:
    def recent_records(self, limit: int = 10) -> list[MemoryRecord]:
        del limit
        return []

    def retrieve(self, query: MemoryQuery, limit: int = 10) -> list[RetrievedMemoryRecord]:
        del query, limit
        return []

    def render_prompt_context(self, query: MemoryQuery, limit: int = 6) -> str:
        del query, limit
        return ""

    def read_scratchpad(self) -> str:
        return ""

    def replace_scratchpad(self, text: str) -> None:
        del text

    def append_scratchpad(self, text: str) -> None:
        del text

    def get(self, key: str, default: object = None) -> object:
        del key
        return default

    def __contains__(self, key: object) -> bool:
        del key
        return False

    def __getitem__(self, key: str) -> object:
        raise KeyError(key)

    def __setitem__(self, key: str, value: object) -> None:
        del key, value


class _LogStub:
    def write(self, record: LogRecord) -> None:
        del record

    def register_review_trigger(self, trigger) -> None:
        del trigger

    def request_review(self, request) -> None:
        del request


def test_cogsguard_semantic_surface_builds_state_and_events(
    cogsguard_env_info,
    make_observation,
    make_tag_token,
    make_token,
) -> None:
    center_row = cogsguard_env_info.obs_height // 2
    center_col = cogsguard_env_info.obs_width // 2
    surface = CogsguardSemanticSurface()

    previous_obs = make_observation(
        cogsguard_env_info,
        [
            make_tag_token(cogsguard_env_info, "team:cogs", row=center_row, col=center_col),
            make_tag_token(cogsguard_env_info, "type:agent", row=center_row, col=center_col),
            make_token(cogsguard_env_info, "inv:aligner", 1, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent_id", 0, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent:group", 0, row=center_row, col=center_col),
        ],
    )
    previous_state = surface.build_state(previous_obs, policy_env_info=cogsguard_env_info, step=7)

    current_obs = make_observation(
        cogsguard_env_info,
        [
            make_tag_token(cogsguard_env_info, "team:cogs", row=center_row, col=center_col),
            make_tag_token(cogsguard_env_info, "type:agent", row=center_row, col=center_col),
            make_token(cogsguard_env_info, "inv:aligner", 1, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "inv:heart", 1, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent_id", 0, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent:group", 0, row=center_row, col=center_col),
            make_tag_token(cogsguard_env_info, "type:junction", row=center_row - 1, col=center_col),
        ],
    )
    current_state = surface.build_state_with_events(
        current_obs,
        policy_env_info=cogsguard_env_info,
        step=8,
        previous_state=previous_state,
    )

    assert current_state.game == "cogsguard"
    assert any(event.event_type == "heart_acquired" for event in current_state.recent_events)
    assert surface.render_state(current_state) == CogsguardPromptAdapter().render_state(current_state)
    assert surface.render_skill_library() == CogsguardPromptAdapter().render_skill_library()


def test_cogsguard_semantic_surface_builds_sdk_with_shared_objectives(
    cogsguard_env_info,
    make_observation,
    make_tag_token,
    make_token,
) -> None:
    center_row = cogsguard_env_info.obs_height // 2
    center_col = cogsguard_env_info.obs_width // 2
    surface = CogsguardSemanticSurface()

    observation = make_observation(
        cogsguard_env_info,
        [
            make_tag_token(cogsguard_env_info, "team:cogs", row=center_row, col=center_col),
            make_tag_token(cogsguard_env_info, "type:agent", row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent_id", 0, row=center_row, col=center_col),
            make_token(cogsguard_env_info, "agent:group", 0, row=center_row, col=center_col),
        ],
    )
    state = surface.build_state(observation, policy_env_info=cogsguard_env_info, step=9).model_copy(
        update={
            "team_summary": TeamSummary(
                team_id="cogs",
                shared_inventory={"carbon": 3},
                shared_objectives=["existing_objective", "current_objective:resource_coverage"],
            )
        }
    )
    actions = ActionCatalog([ActionDescriptor(name="inspect_shared_surface", description="inspect the sdk state")])

    sdk = surface.build_sdk(
        state,
        actions=actions,
        memory=_MemoryStub(),
        log=_LogStub(),
        shared_objectives=["current_objective:resource_coverage", "missing_resource:oxygen"],
    )

    assert sdk.helpers.shared_objectives() == [
        "existing_objective",
        "current_objective:resource_coverage",
        "missing_resource:oxygen",
    ]
    assert sdk.state.team_summary is not None
    assert sdk.state.team_summary.shared_inventory == {"carbon": 3}
    assert [action.name for action in sdk.actions.list_actions()] == ["inspect_shared_surface"]
