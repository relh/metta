from __future__ import annotations

from cog_cyborg.memory.store import MemoryStore
from mettagrid_sdk.sdk import (
    BeliefMemoryRecord,
    MemoryQuery,
    MemoryView,
    MettagridState,
    RetrievedMemoryRecord,
    SemanticEntity,
)

from cog_cognition.planning.models import AgendaPlan, PlannerDecision, ReactionTrigger, SubtaskPlan

_REPLAN_EVENT_TYPES = {
    "enemy_seen",
    "gear_acquired",
    "gear_lost",
    "heart_acquired",
    "heart_lost",
    "junction_owner_changed",
    "path_blocked",
    "region_unsafe",
    "teammate_request",
}
_HEART_REQUIRED_SUBTASKS = {"capture_neutral_junction", "neutralize_enemy_junction"}
_NON_RESOURCE_ITEMS = {"aligner", "energy", "heart", "miner", "scout", "scrambler"}


class HierarchicalPlanner:
    def __init__(self) -> None:
        self._agenda_serial = 0
        self._current_plan: AgendaPlan | None = None

    @property
    def current_plan(self) -> AgendaPlan | None:
        return self._current_plan

    def reset(self) -> None:
        self._current_plan = None

    def decide(
        self,
        state: MettagridState,
        memory: MemoryView,
        *,
        persist_store: MemoryStore | None = None,
    ) -> PlannerDecision:
        query = MemoryQuery.from_state(
            state,
            active_plan=None if self._current_plan is None else self._current_plan.active_subtask.kind,
            extra_tags=_query_tags(self._current_plan),
        )
        supporting_memory = memory.retrieve(query, limit=6)
        triggers = self._detect_triggers(state)
        if self._current_plan is None or triggers:
            plan = self._create_plan(state, supporting_memory)
            self._current_plan = plan
            if persist_store is not None:
                persist_store.append_record(plan.as_memory_record(game=state.game))
            return PlannerDecision(
                mode="replan",
                plan=plan,
                triggers=triggers,
                supporting_memory=supporting_memory,
            )

        self._current_plan.updated_step = state.step
        self._current_plan.supporting_memory_ids = [item.record.record_id for item in supporting_memory]
        note_summaries = _note_summaries(supporting_memory)
        if note_summaries:
            self._current_plan.notes = note_summaries
        return PlannerDecision(
            mode="continue",
            plan=self._current_plan,
            supporting_memory=supporting_memory,
        )

    def _detect_triggers(self, state: MettagridState) -> list[ReactionTrigger]:
        if self._current_plan is None:
            return [ReactionTrigger(trigger_type="no_active_plan", reason="No active plan is active.")]

        triggers = []
        if state.self_state.role != self._current_plan.role_context:
            triggers.append(
                ReactionTrigger(
                    trigger_type="role_changed",
                    reason=f"Role changed from {self._current_plan.role_context} to {state.self_state.role}.",
                )
            )

        if _plan_completed(state, self._current_plan):
            triggers.append(
                ReactionTrigger(
                    trigger_type="subtask_completed",
                    reason=f"Subtask {self._current_plan.active_subtask.kind} completed.",
                    evidence_ids=[self._current_plan.agenda_id],
                )
            )

        invalid_reason = _plan_invalid_reason(state, self._current_plan)
        if invalid_reason is not None:
            triggers.append(
                ReactionTrigger(
                    trigger_type="subtask_invalid",
                    reason=invalid_reason,
                    evidence_ids=[self._current_plan.agenda_id],
                )
            )

        for event in state.recent_events:
            if event.event_type not in _REPLAN_EVENT_TYPES:
                continue
            triggers.append(
                ReactionTrigger(
                    trigger_type=event.event_type,
                    reason=event.summary,
                    evidence_ids=[event.event_id, *event.evidence],
                )
            )
        return _dedupe_triggers(triggers)

    def _create_plan(self, state: MettagridState, supporting_memory: list[RetrievedMemoryRecord]) -> AgendaPlan:
        self._agenda_serial += 1
        role = state.self_state.role or "unknown"
        if state.game == "cogsguard":
            summary, subtask = _cogsguard_plan(state, supporting_memory)
        else:
            summary, subtask = _generic_plan(state, supporting_memory)
        return AgendaPlan(
            agenda_id=f"{state.game}-agenda-{self._agenda_serial}",
            summary=summary,
            role_context=role,
            created_step=state.step,
            updated_step=state.step,
            active_subtask=subtask,
            supporting_memory_ids=[item.record.record_id for item in supporting_memory],
            notes=_note_summaries(supporting_memory),
        )


def _cogsguard_plan(
    state: MettagridState,
    supporting_memory: list[RetrievedMemoryRecord],
) -> tuple[str, SubtaskPlan]:
    role = state.self_state.role or "unknown"
    team_id = state.team_summary.team_id if state.team_summary is not None else ""
    heart_count = _inventory_count(state, "heart")
    friendly_hubs = _matching_entities(state, entity_type="hub", team_id=team_id, disposition="friendly")
    neutral_junctions = _matching_entities(state, entity_type="junction", team_id=team_id, disposition="neutral")
    enemy_junctions = _matching_entities(state, entity_type="junction", team_id=team_id, disposition="enemy")
    enemy_agents = _matching_entities(state, entity_type="agent", team_id=team_id, disposition="enemy")
    extractors = [entity for entity in state.visible_entities if entity.entity_type.endswith("_extractor")]
    frontier_region = _preferred_frontier_region(state, supporting_memory)

    if role == "aligner":
        if heart_count == 0 and neutral_junctions:
            target = _nearest_entity(state, friendly_hubs)
            return (
                "Acquire a heart before attempting to align the next neutral junction.",
                _subtask(
                    kind="acquire_heart",
                    summary="Get a heart from a friendly hub so an aligner capture is possible.",
                    role=role,
                    target=target,
                    extra_tags=["heart", "hub", "junction"],
                    success_conditions=["has_heart"],
                    failure_conditions=["enemy_seen", "role_changed"],
                ),
            )
        if heart_count > 0 and neutral_junctions:
            target = _nearest_entity(state, neutral_junctions)
            return (
                f"Capture {target.entity_id} while the aligner is carrying a heart.",
                _subtask(
                    kind="capture_neutral_junction",
                    summary=f"Use the carried heart to align {target.entity_id}.",
                    role=role,
                    target=target,
                    extra_tags=["heart", "junction", "neutral"],
                    success_conditions=["junction_owner=friendly"],
                    failure_conditions=["heart_lost", "enemy_seen"],
                ),
            )
    if role == "scrambler":
        if heart_count == 0 and enemy_junctions:
            target = _nearest_entity(state, friendly_hubs)
            return (
                "Acquire a heart before attempting to scramble the enemy junction.",
                _subtask(
                    kind="acquire_heart",
                    summary="Get a heart so the scrambler can flip enemy territory.",
                    role=role,
                    target=target,
                    extra_tags=["heart", "hub", "scrambler"],
                    success_conditions=["has_heart"],
                    failure_conditions=["enemy_seen", "role_changed"],
                ),
            )
        if heart_count > 0 and enemy_junctions:
            target = _nearest_entity(state, enemy_junctions)
            return (
                f"Pressure and neutralize {target.entity_id} with the carried heart.",
                _subtask(
                    kind="neutralize_enemy_junction",
                    summary=f"Spend the carried heart to disrupt {target.entity_id}.",
                    role=role,
                    target=target,
                    extra_tags=["enemy", "heart", "junction"],
                    success_conditions=["junction_owner!=enemy"],
                    failure_conditions=["heart_lost", "role_changed"],
                ),
            )
        if enemy_agents:
            target = _nearest_entity(state, enemy_agents)
            return (
                f"Pressure nearby enemy {target.entity_id} to keep them off contested territory.",
                _subtask(
                    kind="pressure_enemy_lane",
                    summary=f"Shadow {target.entity_id} and contest their lane.",
                    role=role,
                    target=target,
                    extra_tags=["enemy", "lane_pressure"],
                    success_conditions=["enemy_not_visible"],
                    failure_conditions=["role_changed"],
                ),
            )
    if role == "miner":
        if _carried_resource_total(state) > 0 and friendly_hubs:
            target = _nearest_entity(state, friendly_hubs)
            return (
                f"Deposit carried resources at {target.entity_id}.",
                _subtask(
                    kind="deposit_resources",
                    summary=f"Deposit the current load at {target.entity_id}.",
                    role=role,
                    target=target,
                    extra_tags=["deposit", "hub", "miner"],
                    success_conditions=["resources_deposited"],
                    failure_conditions=["enemy_seen", "role_changed"],
                ),
            )
        if extractors:
            target = _nearest_entity(state, extractors)
            return (
                f"Collect resources from {target.entity_id} for the team economy.",
                _subtask(
                    kind="collect_resources",
                    summary=f"Gather resources at {target.entity_id}.",
                    role=role,
                    target=target,
                    extra_tags=["extractor", "miner"],
                    success_conditions=["resources_collected"],
                    failure_conditions=["enemy_seen", "role_changed"],
                ),
            )
    if role == "scout" and enemy_agents:
        target = _nearest_entity(state, enemy_agents)
        return (
            f"Shadow {target.entity_id} and keep enemy movement visible.",
            _subtask(
                kind="shadow_enemy",
                summary=f"Track {target.entity_id} to preserve vision on the enemy push.",
                role=role,
                target=target,
                extra_tags=["enemy", "vision", "scout"],
                success_conditions=["enemy_not_visible"],
                failure_conditions=["role_changed"],
            ),
        )
    if frontier_region is not None:
        return (
            f"Advance into {frontier_region} to reveal new tactical options.",
            SubtaskPlan(
                subtask_id=f"subtask:{role}:explore_frontier",
                kind="explore_frontier",
                summary=f"Explore frontier region {frontier_region}.",
                target_tags=sorted({role, "frontier", frontier_region}),
                success_conditions=["frontier_reduced"],
                failure_conditions=["enemy_seen", "role_changed"],
            ),
        )
    regroup_target = _nearest_entity(state, friendly_hubs)
    if regroup_target is not None:
        return (
            f"Regroup at {regroup_target.entity_id} while waiting for a stronger tactical opening.",
            _subtask(
                kind="regroup_at_hub",
                summary=f"Hold near {regroup_target.entity_id} until a better task appears.",
                role=role,
                target=regroup_target,
                extra_tags=["hub", "regroup"],
                success_conditions=["new_objective_visible"],
                failure_conditions=["enemy_seen", "role_changed"],
            ),
        )
    return _generic_plan(state, supporting_memory)


def _generic_plan(
    state: MettagridState,
    supporting_memory: list[RetrievedMemoryRecord],
) -> tuple[str, SubtaskPlan]:
    frontier_region = _preferred_frontier_region(state, supporting_memory)
    role = state.self_state.role or "unknown"
    if frontier_region is not None:
        return (
            f"Explore {frontier_region} to uncover the next actionable objective.",
            SubtaskPlan(
                subtask_id=f"subtask:{role}:explore_frontier",
                kind="explore_frontier",
                summary=f"Explore frontier region {frontier_region}.",
                target_tags=sorted({role, "frontier", frontier_region}),
                success_conditions=["frontier_reduced"],
                failure_conditions=["role_changed"],
            ),
        )
    return (
        "Survey the visible region and wait for a clearer semantic target.",
        SubtaskPlan(
            subtask_id=f"subtask:{role}:survey_visible_region",
            kind="survey_visible_region",
            summary="Hold position while preserving visibility on the local area.",
            target_tags=sorted({role, "survey"}),
            success_conditions=["new_objective_visible"],
            failure_conditions=["role_changed"],
        ),
    )


def _subtask(
    *,
    kind: str,
    summary: str,
    role: str,
    target: SemanticEntity | None,
    extra_tags: list[str],
    success_conditions: list[str],
    failure_conditions: list[str],
) -> SubtaskPlan:
    target_tags = {role, kind, *extra_tags}
    if target is not None:
        target_tags.add(target.entity_type)
        target_tags.update(target.labels)
    return SubtaskPlan(
        subtask_id=f"subtask:{role}:{kind}",
        kind=kind,
        summary=summary,
        target_entity_id=None if target is None else target.entity_id,
        target_owner=None if target is None or "owner" not in target.attributes else str(target.attributes["owner"]),
        target_position=None if target is None else target.position,
        target_tags=sorted(target_tags),
        success_conditions=success_conditions,
        failure_conditions=failure_conditions,
    )


def _query_tags(current_plan: AgendaPlan | None) -> list[str]:
    if current_plan is None:
        return []
    return sorted({current_plan.active_subtask.kind, *current_plan.active_subtask.target_tags})


def _preferred_frontier_region(
    state: MettagridState,
    supporting_memory: list[RetrievedMemoryRecord],
) -> str | None:
    if not state.known_world.frontier_regions:
        return None
    risky_regions = _risky_regions(supporting_memory)
    for region in state.known_world.frontier_regions:
        if region not in risky_regions:
            return region
    return state.known_world.frontier_regions[0]


def _risky_regions(supporting_memory: list[RetrievedMemoryRecord]) -> set[str]:
    risky_regions = set()
    for item in supporting_memory:
        record = item.record
        if not isinstance(record, BeliefMemoryRecord):
            continue
        if "contested" not in record.belief_type and "risky" not in record.belief_type:
            continue
        risky_regions.update(tag for tag in record.tags if tag.endswith("_lane") or tag.endswith("_region"))
    return risky_regions


def _matching_entities(
    state: MettagridState,
    *,
    entity_type: str,
    team_id: str,
    disposition: str,
) -> list[SemanticEntity]:
    return [
        entity
        for entity in state.visible_entities
        if entity.entity_type == entity_type and disposition in entity.labels and _entity_matches_team(entity, team_id)
    ]


def _entity_matches_team(entity: SemanticEntity, team_id: str) -> bool:
    if "neutral" in entity.labels:
        return True
    entity_team = entity.attributes["owner"] if "owner" in entity.attributes else entity.attributes["team"]
    if "friendly" in entity.labels:
        return entity_team == team_id
    if "enemy" in entity.labels:
        return entity_team != team_id
    return True


def _nearest_entity(state: MettagridState, entities: list[SemanticEntity]) -> SemanticEntity | None:
    if not entities:
        return None
    sx = state.self_state.position.x
    sy = state.self_state.position.y
    return min(
        entities,
        key=lambda entity: (abs(entity.position.x - sx) + abs(entity.position.y - sy), entity.entity_id),
    )


def _inventory_count(state: MettagridState, item: str) -> int:
    if item not in state.self_state.inventory:
        return 0
    return state.self_state.inventory[item]


def _carried_resource_total(state: MettagridState) -> int:
    total = 0
    for name, value in state.self_state.inventory.items():
        if name in _NON_RESOURCE_ITEMS or ":" in name:
            continue
        total += value
    return total


def _plan_completed(state: MettagridState, current_plan: AgendaPlan) -> bool:
    kind = current_plan.active_subtask.kind
    team_id = state.team_summary.team_id if state.team_summary is not None else ""
    if kind == "acquire_heart":
        return _inventory_count(state, "heart") > 0
    if kind == "capture_neutral_junction":
        target = _target_entity(state, current_plan)
        return target is not None and str(target.attributes["owner"]) == team_id
    if kind == "neutralize_enemy_junction":
        target = _target_entity(state, current_plan)
        planned_owner = current_plan.active_subtask.target_owner
        assert planned_owner is not None
        return target is not None and str(target.attributes["owner"]) != planned_owner
    if kind == "deposit_resources":
        return _carried_resource_total(state) == 0
    if kind == "collect_resources":
        return _carried_resource_total(state) > 0
    if kind == "explore_frontier":
        target_regions = [
            tag for tag in current_plan.active_subtask.target_tags if tag.endswith("_lane") or tag.endswith("_region")
        ]
        return all(region not in state.known_world.frontier_regions for region in target_regions)
    if kind == "pressure_enemy_lane":
        return not _matching_entities(
            state,
            entity_type="agent",
            team_id=team_id,
            disposition="enemy",
        )
    if kind == "shadow_enemy":
        return _target_entity(state, current_plan) is None
    return False


def _plan_invalid_reason(state: MettagridState, current_plan: AgendaPlan) -> str | None:
    kind = current_plan.active_subtask.kind
    if kind in _HEART_REQUIRED_SUBTASKS and _inventory_count(state, "heart") == 0:
        return f"Subtask {kind} no longer has the required heart."
    if kind == "deposit_resources" and _carried_resource_total(state) == 0:
        return "Deposit plan no longer has carried resources to deliver."
    if kind == "collect_resources" and not any(
        entity.entity_type.endswith("_extractor") for entity in state.visible_entities
    ):
        return "No visible extractor remains for the active collection plan."
    return None


def _target_entity(state: MettagridState, current_plan: AgendaPlan) -> SemanticEntity | None:
    target_entity_id = current_plan.active_subtask.target_entity_id
    if target_entity_id is None:
        return None
    for entity in state.visible_entities:
        if entity.entity_id == target_entity_id:
            return entity
    return None


def _note_summaries(supporting_memory: list[RetrievedMemoryRecord]) -> list[str]:
    notes = []
    seen = set()
    for item in supporting_memory:
        if not isinstance(item.record, BeliefMemoryRecord) and item.record.importance < 0.7:
            continue
        if item.record.summary in seen:
            continue
        notes.append(item.record.summary)
        seen.add(item.record.summary)
        if len(notes) == 3:
            break
    return notes


def _dedupe_triggers(triggers: list[ReactionTrigger]) -> list[ReactionTrigger]:
    deduped = []
    seen = set()
    for trigger in triggers:
        key = (trigger.trigger_type, trigger.reason)
        if key in seen:
            continue
        deduped.append(trigger)
        seen.add(key)
    return deduped
