from __future__ import annotations

from typing import cast

from mettagrid_sdk.sdk import (
    ActionDescriptor,
    ActionOutcome,
    GridPosition,
    HelperCapability,
    KnownWorldState,
    LogRecord,
    MacroDirective,
    MemoryQuery,
    MemoryRecord,
    MettagridSDK,
    MettagridState,
    RetrievedMemoryRecord,
    ReviewRequest,
    ReviewTrigger,
    SelfState,
    SemanticEntity,
    SemanticEvent,
    StateHelperCatalog,
    TeamMemberSummary,
    TeamSummary,
)


class FakeActions:
    def __init__(self) -> None:
        self._actions = [
            ActionDescriptor(
                name="pickup_heart",
                description="Acquire a heart from the nearest valid site.",
                preconditions=["adjacent_to_heart_source"],
                terminal_reasons=["success", "no_heart_available"],
            )
        ]

    def list_actions(self) -> list[ActionDescriptor]:
        return self._actions


class FakeHelpers:
    def __init__(self) -> None:
        self._capabilities = [
            HelperCapability(name="resolve_target", description="Select the best current semantic target.")
        ]

    def list_capabilities(self) -> list[HelperCapability]:
        return self._capabilities

    def render_capability_summary(self, max_items: int | None = None) -> str:
        capabilities = self._capabilities if max_items is None else self._capabilities[:max_items]
        return "\n".join(f"- {item.name}: {item.description}" for item in capabilities)

    def agent_id(self) -> int:
        return 1

    def shared_inventory(self) -> dict[str, int]:
        return {"heart": 1}

    def shared_objectives(self) -> list[str]:
        return ["capture_more_junctions"]

    def seen_resources(self) -> list[str]:
        return ["carbon"]

    def missing_resources(self) -> list[str]:
        return ["oxygen"]

    def self_attribute(
        self,
        name: str,
        default: str | int | float | bool | None = None,
    ) -> str | int | float | bool | None:
        if name == "agent_id":
            return 1
        return default

    def position(self) -> tuple[int, int]:
        return (0, 0)

    def visible_entity_counts(self) -> dict[str, int]:
        return {"junction": 1}

    def recent_event_types(self) -> list[str]:
        return ["heart_acquired"]

    def visible_entities(
        self,
        entity_type: str | None = None,
        label: str | None = None,
        max_distance: int | None = None,
    ) -> list[SemanticEntity]:
        return []

    def visible_entity_ids(
        self,
        entity_type: str | None = None,
        label: str | None = None,
        max_distance: int | None = None,
    ) -> list[str]:
        return []

    def entity_by_id(self, entity_id: str) -> SemanticEntity | None:
        return None

    def nearest_visible_entity(
        self,
        entity_type: str | None = None,
        label: str | None = None,
        max_distance: int | None = None,
    ) -> SemanticEntity | None:
        return None

    def distance_to_entity(self, entity_id: str) -> int | None:
        return None


class FakeMemory:
    def __init__(self) -> None:
        self._records = [MemoryRecord(record_id="evt-1", kind="event", summary="Picked up a heart.")]
        self._scratchpad = "Hold the east lane."

    def recent_records(self, limit: int = 10) -> list[MemoryRecord]:
        return self._records[:limit]

    def retrieve(self, query: MemoryQuery, limit: int = 10) -> list[RetrievedMemoryRecord]:
        return [
            RetrievedMemoryRecord(
                record=self._records[0],
                score=0.9,
                relevance_score=0.9,
                recency_score=0.0,
                importance_score=0.0,
            )
        ][:limit]

    def render_prompt_context(self, query: MemoryQuery, limit: int = 6) -> str:
        return "=== RETRIEVED SEMANTIC MEMORY ===\n  - [event] step=None Picked up a heart."

    def read_scratchpad(self) -> str:
        return self._scratchpad

    def replace_scratchpad(self, text: str) -> None:
        self._scratchpad = text

    def append_scratchpad(self, text: str) -> None:
        self._scratchpad += text

    def get(self, key: str, default: object = None) -> object:
        prefix = f"{key}: "
        for line in self._scratchpad.splitlines():
            if line.startswith(prefix):
                return line[len(prefix) :]
        return default

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and self.get(key, None) is not None

    def __getitem__(self, key: str) -> object:
        value = self.get(key, None)
        if value is None:
            raise KeyError(key)
        return value

    def __setitem__(self, key: str, value: object) -> None:
        prefix = f"{key}: "
        lines = []
        replaced = False
        for line in self._scratchpad.splitlines():
            if line.startswith(prefix):
                lines.append(f"{key}: {value}")
                replaced = True
            else:
                lines.append(line)
        if not replaced:
            lines.append(f"{key}: {value}")
        self._scratchpad = "\n".join(lines)


class FakeLog:
    def __init__(self) -> None:
        self.records: list[LogRecord] = []
        self.triggers: list[ReviewTrigger] = []
        self.requests: list[ReviewRequest] = []

    def write(self, record: LogRecord) -> None:
        self.records.append(record)

    def register_review_trigger(self, trigger: ReviewTrigger) -> None:
        self.triggers.append(trigger)

    def request_review(self, request: ReviewRequest) -> None:
        self.requests.append(request)


class FakePlan:
    def __init__(self) -> None:
        self._plan = "# Plan\n- Hold the east lane"

    def read_plan(self, max_chars: int = 4000) -> str:
        return self._plan[-max_chars:]

    def replace_plan(self, text: str) -> None:
        self._plan = text

    def append_plan(self, text: str) -> None:
        self._plan += text


def test_mettagrid_sdk_contracts_hold_semantic_state() -> None:
    state = MettagridState(
        game="cogsguard",
        self_state=SelfState(
            entity_id="agent-1",
            entity_type="self",
            position=GridPosition(x=3, y=-1),
            labels=["aligner", "friendly"],
            role="aligner",
            inventory={"heart": 1, "influence": 2},
            status=["ready_to_capture"],
        ),
        visible_entities=[
            SemanticEntity(
                entity_id="junction-7",
                entity_type="junction",
                position=GridPosition(x=5, y=-1),
                labels=["neutral"],
                attributes={"owner": "neutral"},
            )
        ],
        known_world=KnownWorldState(frontier_regions=["east_lane"], explored_regions=["spawn"]),
        team_summary=TeamSummary(
            team_id="aligned",
            members=[
                TeamMemberSummary(
                    entity_id="agent-2",
                    role="miner",
                    position=GridPosition(x=0, y=0),
                    status=["collecting"],
                )
            ],
            shared_objectives=["capture_more_junctions"],
        ),
        recent_events=[
            SemanticEvent(
                event_id="evt-1",
                event_type="heart_acquired",
                step=12,
                location=GridPosition(x=3, y=-1),
                importance=0.9,
                summary="Agent picked up a heart.",
            )
        ],
    )

    sdk = MettagridSDK(
        state=state,
        actions=FakeActions(),
        helpers=FakeHelpers(),
        memory=FakeMemory(),
        log=FakeLog(),
    )

    sdk.log.write(LogRecord(level="info", message="phase1-smoke"))

    assert sdk.state.game == "cogsguard"
    assert sdk.actions.list_actions()[0].name == "pickup_heart"
    assert sdk.helpers.list_capabilities()[0].name == "resolve_target"
    assert sdk.memory.recent_records()[0].record_id == "evt-1"
    assert sdk.memory.read_scratchpad() == "Hold the east lane."
    assert cast(FakeLog, sdk.log).records[0].message == "phase1-smoke"


def test_sdk_supports_review_triggers_and_mutable_scratchpad() -> None:
    memory = FakeMemory()
    log = FakeLog()
    sdk = MettagridSDK(
        state=MettagridState(
            game="cogsguard",
            self_state=SelfState(entity_id="agent-1", entity_type="agent", position=GridPosition(x=0, y=0)),
        ),
        actions=FakeActions(),
        helpers=FakeHelpers(),
        memory=memory,
        log=log,
    )

    sdk.memory.append_scratchpad("\nAvoid overcommitting without hearts.")
    sdk.log.register_review_trigger(
        ReviewTrigger(name="enemy_lane_seen", prompt="Re-evaluate lane assignment.", target="policy")
    )
    sdk.log.request_review(
        ReviewRequest(trigger_name="enemy_lane_seen", prompt="Enemy appeared in the east lane.", target="memory")
    )

    assert "Avoid overcommitting" in sdk.memory.read_scratchpad()
    assert log.triggers[0].name == "enemy_lane_seen"
    assert log.requests[0].target == "memory"


def test_sdk_exposes_scratchpad_helpers() -> None:
    memory = FakeMemory()
    plan = FakePlan()
    sdk = MettagridSDK(
        state=MettagridState(
            game="cogsguard",
            self_state=SelfState(entity_id="agent-1", entity_type="agent", position=GridPosition(x=0, y=0)),
        ),
        actions=FakeActions(),
        helpers=FakeHelpers(),
        memory=memory,
        log=FakeLog(),
        plan=plan,
    )

    assert sdk.scratchpad == "Hold the east lane."
    assert sdk.read_scratchpad() == "Hold the east lane."
    assert sdk.read_plan() == "# Plan\n- Hold the east lane"

    sdk.replace_scratchpad("Phase: bootstrap")
    sdk.append_scratchpad("\nKeep mining carbon.")
    sdk.replace_plan("# Plan\n- Bootstrap hearts")
    sdk.append_plan("\n- Rotate into aligners")

    assert memory.read_scratchpad() == "Phase: bootstrap\nKeep mining carbon."
    assert plan.read_plan() == "# Plan\n- Bootstrap hearts\n- Rotate into aligners"


def test_action_outcome_tracks_terminal_reason() -> None:
    outcome = ActionOutcome(
        action="capture_neutral_junction",
        success=False,
        reason="missing_heart",
        step_started=20,
        step_finished=24,
        evidence=["inventory.heart=0", "junction.owner=neutral"],
    )

    assert outcome.reason == "missing_heart"
    assert outcome.step_finished == 24


def test_log_record_can_carry_a_typed_review_request() -> None:
    record = LogRecord(
        level="warning",
        message="Still mining the same extractor after repeated stalls.",
        step=24,
        review=ReviewRequest(
            trigger_name="extractor_fixation",
            prompt="Rewrite the opening so the cog changes focus or phase.",
            target="policy",
        ),
        data={"subtask": "mine_germanium"},
    )

    assert record.review is not None
    assert record.review.trigger_name == "extractor_fixation"
    assert record.data["subtask"] == "mine_germanium"


def test_macro_directive_tracks_high_level_overrides() -> None:
    directive = MacroDirective(
        role="miner",
        resource_bias="oxygen",
        objective="resource_coverage",
        note="opening coverage",
        metadata={"phase": "opening"},
    )

    assert directive.role == "miner"
    assert directive.resource_bias == "oxygen"
    assert directive.is_empty() is False


def test_state_helper_catalog_exposes_team_and_agent_state() -> None:
    state = MettagridState(
        game="cogsguard",
        self_state=SelfState(
            entity_id="agent-3",
            entity_type="agent",
            position=GridPosition(x=0, y=0),
            attributes={"agent_id": 3, "lane": "west"},
        ),
        team_summary=TeamSummary(
            team_id="cogs",
            shared_inventory={"carbon": 4},
            shared_objectives=["seen_resource:carbon", "missing_resource:oxygen", "phase:opening"],
        ),
    )
    helpers = StateHelperCatalog(state)

    assert helpers.agent_id() == 3
    assert helpers.shared_inventory() == {"carbon": 4}
    assert helpers.shared_objectives() == ["seen_resource:carbon", "missing_resource:oxygen", "phase:opening"]
    assert helpers.seen_resources() == ["carbon"]
    assert helpers.missing_resources() == ["oxygen"]
    assert helpers.self_attribute("lane") == "west"
    assert helpers.position() == (0, 0)
    assert helpers.visible_entity_counts() == {}
    assert helpers.recent_event_types() == []
    assert "visible_entity_counts" in helpers.render_capability_summary()
    assert "current_objectives" not in helpers.render_capability_summary()


def test_state_helper_catalog_summarizes_visible_entities_and_recent_events() -> None:
    state = MettagridState(
        game="cogsguard",
        self_state=SelfState(
            entity_id="agent-3",
            entity_type="agent",
            position=GridPosition(x=4, y=-2),
            attributes={"agent_id": 3},
        ),
        visible_entities=[
            SemanticEntity(
                entity_id="junction-1",
                entity_type="junction",
                position=GridPosition(x=1, y=0),
                labels=["neutral"],
                attributes={},
            ),
            SemanticEntity(
                entity_id="junction-2",
                entity_type="junction",
                position=GridPosition(x=2, y=0),
                labels=["enemy"],
                attributes={},
            ),
            SemanticEntity(
                entity_id="hub-1",
                entity_type="hub",
                position=GridPosition(x=0, y=1),
                labels=["friendly"],
                attributes={},
            ),
        ],
        recent_events=[
            SemanticEvent(
                event_id="evt-1",
                event_type="enemy_seen",
                step=10,
                location=GridPosition(x=1, y=0),
                importance=0.8,
                summary="Enemy appeared.",
            ),
            SemanticEvent(
                event_id="evt-2",
                event_type="enemy_seen",
                step=11,
                location=GridPosition(x=2, y=0),
                importance=0.7,
                summary="Enemy remained visible.",
            ),
            SemanticEvent(
                event_id="evt-3",
                event_type="heart_acquired",
                step=12,
                location=GridPosition(x=4, y=-2),
                importance=0.9,
                summary="Heart acquired.",
            ),
        ],
    )

    helpers = StateHelperCatalog(state)

    assert helpers.position() == (4, -2)
    assert helpers.visible_entity_counts() == {"hub": 1, "junction": 2}
    assert helpers.recent_event_types() == ["enemy_seen", "heart_acquired"]


def test_state_helper_catalog_exposes_visible_entity_queries() -> None:
    state = MettagridState(
        game="cogsguard",
        self_state=SelfState(
            entity_id="agent-3",
            entity_type="agent",
            position=GridPosition(x=0, y=0),
            attributes={"agent_id": 3},
        ),
        visible_entities=[
            SemanticEntity(
                entity_id="junction-1",
                entity_type="junction",
                position=GridPosition(x=1, y=0),
                labels=["neutral"],
                attributes={"owner": "neutral"},
            ),
            SemanticEntity(
                entity_id="junction-2",
                entity_type="junction",
                position=GridPosition(x=3, y=0),
                labels=["enemy"],
                attributes={"owner": "clips"},
            ),
            SemanticEntity(
                entity_id="hub-1",
                entity_type="hub",
                position=GridPosition(x=0, y=2),
                labels=["friendly"],
                attributes={"owner": "cogs"},
            ),
        ],
    )

    helpers = StateHelperCatalog(state)

    assert [entity.entity_id for entity in helpers.visible_entities(entity_type="junction")] == [
        "junction-1",
        "junction-2",
    ]
    assert helpers.visible_entity_ids(label="neutral") == ["junction-1"]
    assert helpers.visible_entity_ids(max_distance=2) == ["junction-1", "hub-1"]
    assert helpers.entity_by_id("hub-1") is not None
    assert helpers.entity_by_id("missing") is None
    assert helpers.distance_to_entity("junction-2") == 3
    assert helpers.distance_to_entity("missing") is None
    assert helpers.nearest_visible_entity(entity_type="junction", label="enemy") is not None
    assert helpers.nearest_visible_entity(entity_type="junction", label="enemy").entity_id == "junction-2"
    assert helpers.nearest_visible_entity(entity_type="extractor") is None
    assert "nearest_visible_entity" in helpers.render_capability_summary()


def test_state_helper_catalog_tolerates_non_numeric_agent_id() -> None:
    state = MettagridState(
        game="cogsguard",
        self_state=SelfState(
            entity_id="agent-x",
            entity_type="agent",
            position=GridPosition(x=0, y=0),
            attributes={"agent_id": "abc"},
        ),
    )

    assert StateHelperCatalog(state).agent_id() == 0
