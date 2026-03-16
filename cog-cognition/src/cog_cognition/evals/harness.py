from __future__ import annotations

from cog_cyborg.memory.store import MemoryStore
from mettagrid_sdk.sdk import (
    BeliefMemoryRecord,
    MemoryQuery,
    MemoryView,
    MettagridState,
    SemanticEntity,
)

from cog_cognition.evals.models import (
    BehavioralScenario,
    InterviewProbeAnswer,
    InterviewProbeRequest,
    ScenarioResult,
    ScenarioStepResult,
)
from cog_cognition.planning import HierarchicalPlanner, PlannerDecision

_NON_RESOURCE_ITEMS = {
    "agent_id",
    "aligner",
    "energy",
    "heart",
    "miner",
    "owner",
    "role",
    "scout",
    "scrambler",
    "team",
}


class PlannerEvaluationHarness:
    def __init__(self, planner: HierarchicalPlanner | None = None) -> None:
        self._planner = planner or HierarchicalPlanner()

    def run_scenario(
        self,
        scenario: BehavioralScenario,
        memory: MemoryView,
        *,
        persist_store: MemoryStore | None = None,
    ) -> ScenarioResult:
        self._planner.reset()
        steps = []
        for index, state in enumerate(scenario.states):
            decision = self._planner.decide(state, memory, persist_store=persist_store)
            steps.append(ScenarioStepResult(step_index=index, state_step=state.step, decision=decision))
        return ScenarioResult(name=scenario.name, steps=steps)

    def answer_probe(
        self,
        request: InterviewProbeRequest,
        memory: MemoryView,
        *,
        persist_store: MemoryStore | None = None,
    ) -> InterviewProbeAnswer:
        self._planner.reset()
        decision = self._planner.decide(request.state, memory, persist_store=persist_store)
        if request.question_type == "what_next":
            return _what_next_answer(request, decision)
        if request.question_type == "abandon_triggers":
            return _abandon_triggers_answer(request, decision)
        if request.question_type == "best_teammate_to_deposit_now":
            return _best_teammate_to_deposit_answer(request, decision)
        return _why_not_target_answer(request, decision, memory)


def _what_next_answer(request: InterviewProbeRequest, decision: PlannerDecision) -> InterviewProbeAnswer:
    reasons = [decision.plan.active_subtask.summary, *decision.plan.notes]
    return InterviewProbeAnswer(
        question_type=request.question_type,
        answer=f"{decision.plan.summary} Execute {decision.plan.active_subtask.kind} next.",
        plan_summary=decision.plan.summary,
        subtask_kind=decision.plan.active_subtask.kind,
        target_entity_id=decision.plan.active_subtask.target_entity_id,
        reasons=reasons,
        evidence_ids=decision.plan.supporting_memory_ids,
    )


def _abandon_triggers_answer(request: InterviewProbeRequest, decision: PlannerDecision) -> InterviewProbeAnswer:
    reasons = list(decision.plan.active_subtask.failure_conditions)
    if not reasons:
        reasons = ["role_changed", "subtask_invalid", "subtask_completed"]
    answer = f"Abandon {decision.plan.active_subtask.kind} if any of these conditions fire: {', '.join(reasons)}."
    return InterviewProbeAnswer(
        question_type=request.question_type,
        answer=answer,
        plan_summary=decision.plan.summary,
        subtask_kind=decision.plan.active_subtask.kind,
        target_entity_id=decision.plan.active_subtask.target_entity_id,
        reasons=reasons,
        evidence_ids=decision.plan.supporting_memory_ids,
    )


def _best_teammate_to_deposit_answer(
    request: InterviewProbeRequest,
    decision: PlannerDecision,
) -> InterviewProbeAnswer:
    state = request.state
    team_id = state.team_summary.team_id if state.team_summary is not None else ""
    friendly_hubs = [
        entity for entity in state.visible_entities if entity.entity_type == "hub" and "friendly" in entity.labels
    ]
    teammate_candidates = [
        entity
        for entity in state.visible_entities
        if entity.entity_type == "agent"
        and "friendly" in entity.labels
        and entity.entity_id != state.self_state.entity_id
    ]
    scored_teammates = sorted(
        (
            _deposit_candidate_score(state, entity, friendly_hubs),
            entity,
        )
        for entity in teammate_candidates
        if _resource_total(entity) > 0 and entity.attributes["team"] == team_id
    )
    if not scored_teammates:
        return InterviewProbeAnswer(
            question_type=request.question_type,
            answer="No visible teammate is currently positioned to deposit resources better than the current agent.",
            plan_summary=decision.plan.summary,
            subtask_kind=decision.plan.active_subtask.kind,
            reasons=["no_visible_friendly_carrier"],
            evidence_ids=[],
        )

    _, teammate = scored_teammates[0]
    hub = _nearest_entity(teammate.position.x, teammate.position.y, friendly_hubs)
    resource_total = _resource_total(teammate)
    distance_text = "unknown distance"
    evidence_ids = [teammate.entity_id]
    reasons = [f"carrying {resource_total} resources"]
    if hub is not None:
        distance = _distance(teammate.position.x, teammate.position.y, hub.position.x, hub.position.y)
        distance_text = f"{distance} tiles from {hub.entity_id}"
        evidence_ids.append(hub.entity_id)
        reasons.append(distance_text)
    return InterviewProbeAnswer(
        question_type=request.question_type,
        answer=(
            f"{teammate.entity_id} is best positioned to deposit now because it is "
            f"{distance_text} and carrying {resource_total} resources."
        ),
        plan_summary=decision.plan.summary,
        subtask_kind=decision.plan.active_subtask.kind,
        subject_entity_id=teammate.entity_id,
        reasons=reasons,
        evidence_ids=evidence_ids,
    )


def _why_not_target_answer(
    request: InterviewProbeRequest,
    decision: PlannerDecision,
    memory: MemoryView,
) -> InterviewProbeAnswer:
    target_entity = _entity_by_id(request.state, request.target_entity_id)
    reasons = []
    evidence_ids = list(decision.plan.supporting_memory_ids)
    if target_entity is None:
        reasons.append("target_not_visible")
        return InterviewProbeAnswer(
            question_type=request.question_type,
            answer="That target is not currently visible, so it is not a safe immediate target.",
            plan_summary=decision.plan.summary,
            subtask_kind=decision.plan.active_subtask.kind,
            target_entity_id=request.target_entity_id,
            reasons=reasons,
            evidence_ids=evidence_ids,
        )

    if target_entity.entity_type == "junction":
        reasons.extend(_junction_target_reasons(request.state, target_entity, decision))

    target_query = MemoryQuery.from_state(
        request.state,
        active_plan=decision.plan.active_subtask.kind,
        extra_tags=[target_entity.entity_type, target_entity.entity_id, *target_entity.labels],
    )
    for item in memory.retrieve(target_query, limit=4):
        if not isinstance(item.record, BeliefMemoryRecord):
            continue
        if "contested" not in item.record.belief_type and "risky" not in item.record.belief_type:
            continue
        reasons.append(item.record.summary)
        evidence_ids.append(item.record.record_id)

    if not reasons:
        current_target = decision.plan.active_subtask.target_entity_id
        if current_target is not None and current_target != target_entity.entity_id:
            reasons.append(f"planner_prioritizes:{current_target}")
        else:
            reasons.append("current_plan_has_better_semantic_fit")

    return InterviewProbeAnswer(
        question_type=request.question_type,
        answer=f"{target_entity.entity_id} is not the best target right now because {'; '.join(reasons)}.",
        plan_summary=decision.plan.summary,
        subtask_kind=decision.plan.active_subtask.kind,
        target_entity_id=target_entity.entity_id,
        reasons=reasons,
        evidence_ids=evidence_ids,
    )


def _junction_target_reasons(
    state: MettagridState,
    target_entity: SemanticEntity,
    decision: PlannerDecision,
) -> list[str]:
    role = state.self_state.role
    owner = str(target_entity.attributes["owner"])
    team_id = state.team_summary.team_id if state.team_summary is not None else ""
    reasons = []
    if owner == team_id:
        reasons.append("already_friendly")
    if owner == "neutral" and role != "aligner":
        reasons.append("requires_aligner")
    if owner not in {"neutral", team_id} and role != "scrambler":
        reasons.append("requires_scrambler")
    if owner == "neutral" and role == "aligner" and _inventory_count(state, "heart") == 0:
        reasons.append("missing_heart")
    if owner != team_id and decision.plan.active_subtask.kind == "acquire_heart":
        reasons.append("planner_requires_heart_first")
    return reasons


def _deposit_candidate_score(
    state: MettagridState,
    entity: SemanticEntity,
    friendly_hubs: list[SemanticEntity],
) -> tuple[int, int, str]:
    resource_total = _resource_total(entity)
    hub = _nearest_entity(entity.position.x, entity.position.y, friendly_hubs)
    if hub is None:
        distance = 9999
    else:
        distance = _distance(entity.position.x, entity.position.y, hub.position.x, hub.position.y)
    role_bonus = 0 if str(entity.attributes["role"]) == "miner" else 1
    self_distance = _distance(
        state.self_state.position.x,
        state.self_state.position.y,
        entity.position.x,
        entity.position.y,
    )
    return (-resource_total, distance, f"{role_bonus}:{self_distance}:{entity.entity_id}")


def _resource_total(entity: SemanticEntity) -> int:
    total = 0
    for name, value in entity.attributes.items():
        if name in _NON_RESOURCE_ITEMS or ":" in name or isinstance(value, bool):
            continue
        if isinstance(value, int):
            total += value
    return total


def _entity_by_id(state: MettagridState, entity_id: str | None) -> SemanticEntity | None:
    if entity_id is None:
        return None
    for entity in state.visible_entities:
        if entity.entity_id == entity_id:
            return entity
    return None


def _nearest_entity(x: int, y: int, entities: list[SemanticEntity]) -> SemanticEntity | None:
    if not entities:
        return None
    return min(entities, key=lambda entity: (_distance(x, y, entity.position.x, entity.position.y), entity.entity_id))


def _distance(x0: int, y0: int, x1: int, y1: int) -> int:
    return abs(x0 - x1) + abs(y0 - y1)


def _inventory_count(state: MettagridState, item: str) -> int:
    if item not in state.self_state.inventory:
        return 0
    return state.self_state.inventory[item]
