from __future__ import annotations

from cog_cyborg.policy.semantic_cog import SemanticCogAgentPolicy
from mettagrid_sdk.sdk import MettagridState, SemanticEntity

from cog_cognition.evals.semantic_models import (
    SemanticBehavioralScenario,
    SemanticInterviewProbeAnswer,
    SemanticInterviewProbeRequest,
    SemanticPolicyDecision,
    SemanticScenarioResult,
    SemanticScenarioStepResult,
)

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


class SemanticPolicyEvaluationHarness:
    def __init__(self, policy: SemanticCogAgentPolicy) -> None:
        self._policy = policy

    def run_scenario(self, scenario: SemanticBehavioralScenario) -> SemanticScenarioResult:
        self._policy.reset()
        steps = [
            SemanticScenarioStepResult(
                step_index=index,
                state_step=state.step,
                decision=self.evaluate_state(state),
            )
            for index, state in enumerate(scenario.states)
        ]
        return SemanticScenarioResult(name=scenario.name, steps=steps)

    def evaluate_state(self, state: MettagridState) -> SemanticPolicyDecision:
        action = self._policy.evaluate_state(state)
        return SemanticPolicyDecision(
            action_name=action.name,
            role=str(self._policy.infos.get("role", "")),
            summary=str(self._policy.infos.get("summary", "")),
            phase=str(self._policy.infos.get("phase", "")),
            target_kind=str(self._policy.infos.get("target_kind", "")),
            target_position=str(self._policy.infos.get("target_position", "")),
        )

    def answer_probe(self, request: SemanticInterviewProbeRequest) -> SemanticInterviewProbeAnswer:
        self._policy.reset()
        decision = self.evaluate_state(request.state)
        if request.question_type == "what_next":
            return _what_next_answer(decision)
        if request.question_type == "best_teammate_to_deposit_now":
            return _best_teammate_to_deposit_answer(request.state, decision)
        return _why_not_target_answer(request, decision)


def _what_next_answer(decision: SemanticPolicyDecision) -> SemanticInterviewProbeAnswer:
    return SemanticInterviewProbeAnswer(
        question_type="what_next",
        answer=f"Execute {decision.summary} next as {decision.role}.",
        role=decision.role,
        summary=decision.summary,
        target_entity_id=_target_entity_id(decision),
        reasons=[decision.phase] if decision.phase else [],
    )


def _best_teammate_to_deposit_answer(
    state: MettagridState,
    decision: SemanticPolicyDecision,
) -> SemanticInterviewProbeAnswer:
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
        and entity.attributes.get("team") == team_id
        and _resource_total(entity) > 0
    ]
    if not teammate_candidates:
        return SemanticInterviewProbeAnswer(
            question_type="best_teammate_to_deposit_now",
            answer="No visible teammate is currently positioned to deposit resources better than the current agent.",
            role=decision.role,
            summary=decision.summary,
            reasons=["no_visible_friendly_carrier"],
        )

    teammate = min(
        teammate_candidates,
        key=lambda entity: _deposit_candidate_score(state, entity, friendly_hubs),
    )
    hub = _nearest_entity(teammate.position.x, teammate.position.y, friendly_hubs)
    resource_total = _resource_total(teammate)
    reasons = [f"carrying {resource_total} resources"]
    distance_text = "unknown distance"
    if hub is not None:
        distance = _distance(teammate.position.x, teammate.position.y, hub.position.x, hub.position.y)
        distance_text = f"{distance} tiles from {hub.entity_id}"
        reasons.append(distance_text)
    return SemanticInterviewProbeAnswer(
        question_type="best_teammate_to_deposit_now",
        answer=(
            f"{teammate.entity_id} is best positioned to deposit now because it is "
            f"{distance_text} and carrying {resource_total} resources."
        ),
        role=decision.role,
        summary=decision.summary,
        subject_entity_id=teammate.entity_id,
        reasons=reasons,
    )


def _why_not_target_answer(
    request: SemanticInterviewProbeRequest,
    decision: SemanticPolicyDecision,
) -> SemanticInterviewProbeAnswer:
    target_entity = _entity_by_id(request.state, request.target_entity_id)
    if target_entity is None:
        return SemanticInterviewProbeAnswer(
            question_type="why_not_target",
            answer="That target is not currently visible, so it is not a safe immediate target.",
            role=decision.role,
            summary=decision.summary,
            target_entity_id=request.target_entity_id,
            reasons=["target_not_visible"],
        )

    reasons = _target_reasons(request.state, target_entity, decision)
    if not reasons:
        reasons.append("current_policy_has_better_semantic_fit")

    return SemanticInterviewProbeAnswer(
        question_type="why_not_target",
        answer=f"{target_entity.entity_id} is not the best target right now because {'; '.join(reasons)}.",
        role=decision.role,
        summary=decision.summary,
        target_entity_id=target_entity.entity_id,
        reasons=reasons,
    )


def _target_reasons(
    state: MettagridState,
    target_entity: SemanticEntity,
    decision: SemanticPolicyDecision,
) -> list[str]:
    team_id = state.team_summary.team_id if state.team_summary is not None else ""
    owner = str(target_entity.attributes.get("owner", ""))
    reasons = []
    if target_entity.entity_type == "junction":
        if owner == team_id:
            reasons.append("already_friendly")
        if owner in {"", "neutral"} and decision.role != "aligner":
            reasons.append("requires_aligner")
        if owner not in {"", "neutral", team_id} and decision.role != "scrambler":
            reasons.append("requires_scrambler")
        if owner in {"", "neutral"} and decision.role == "aligner" and _inventory_count(state, "heart") == 0:
            reasons.append("missing_heart")
        if decision.summary == "acquire_heart":
            reasons.append("policy_requires_heart_first")

    target_position = _target_position(target_entity)
    if decision.target_position and decision.target_position != target_position:
        reasons.append(f"policy_prioritizes:{decision.target_position}")
    return reasons


def _target_entity_id(decision: SemanticPolicyDecision) -> str | None:
    if not decision.target_kind or not decision.target_position:
        return None
    return f"{decision.target_kind}@{decision.target_position}"


def _deposit_candidate_score(
    state: MettagridState,
    entity: SemanticEntity,
    friendly_hubs: list[SemanticEntity],
) -> tuple[int, int, int, int, str]:
    resource_total = _resource_total(entity)
    teammate_x = entity.position.x
    teammate_y = entity.position.y
    hub = _nearest_entity(teammate_x, teammate_y, friendly_hubs)
    distance = 9999 if hub is None else _distance(teammate_x, teammate_y, hub.position.x, hub.position.y)
    role_bonus = 0 if str(entity.attributes.get("role", "")) == "miner" else 1
    self_distance = _distance(
        state.self_state.position.x,
        state.self_state.position.y,
        teammate_x,
        teammate_y,
    )
    return (-resource_total, distance, role_bonus, self_distance, entity.entity_id)


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
    return int(state.self_state.inventory.get(item, 0))


def _target_position(entity: SemanticEntity) -> str:
    x = int(entity.attributes.get("global_x", entity.position.x))
    y = int(entity.attributes.get("global_y", entity.position.y))
    return f"{x},{y}"
