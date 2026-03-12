from __future__ import annotations

from mettagrid_sdk.games.base import SemanticEventExtractor
from mettagrid_sdk.sdk import MettagridState, SemanticEntity, SemanticEvent

_GEAR_ITEMS = ("aligner", "miner", "scrambler", "scout")


class CogsguardEventExtractor(SemanticEventExtractor):
    def extract_events(
        self,
        previous_state: MettagridState | None,
        current_state: MettagridState,
    ) -> list[SemanticEvent]:
        if previous_state is None:
            return []

        step = current_state.step or 0
        events: list[SemanticEvent] = []
        previous_hearts = _heart_count(previous_state)
        current_hearts = _heart_count(current_state)
        if previous_hearts == 0 and current_hearts > 0:
            events.append(
                SemanticEvent(
                    event_id=f"heart_acquired:{step}",
                    event_type="heart_acquired",
                    step=step,
                    location=current_state.self_state.position,
                    importance=0.9,
                    summary="Agent acquired a heart.",
                    evidence=[f"heart={current_hearts}"],
                )
            )
        if current_hearts < previous_hearts:
            events.append(
                SemanticEvent(
                    event_id=f"heart_lost:{step}",
                    event_type="heart_lost",
                    step=step,
                    location=current_state.self_state.position,
                    importance=0.8,
                    summary="Agent lost or spent a heart.",
                    evidence=[f"previous_heart={previous_hearts}", f"current_heart={current_hearts}"],
                )
            )

        for gear in _GEAR_ITEMS:
            previous_count = _inventory_count(previous_state, gear)
            current_count = _inventory_count(current_state, gear)
            if current_count > previous_count:
                events.append(
                    SemanticEvent(
                        event_id=f"gear_acquired:{gear}:{step}",
                        event_type="gear_acquired",
                        step=step,
                        location=current_state.self_state.position,
                        importance=0.7,
                        summary=f"Agent acquired {gear} gear.",
                        evidence=[f"gear={gear}", f"count={current_count}"],
                    )
                )
            if current_count < previous_count:
                events.append(
                    SemanticEvent(
                        event_id=f"gear_lost:{gear}:{step}",
                        event_type="gear_lost",
                        step=step,
                        location=current_state.self_state.position,
                        importance=0.7,
                        summary=f"Agent lost {gear} gear.",
                        evidence=[f"gear={gear}", f"count={current_count}"],
                    )
                )

        previous_enemy_ids = {entity.entity_id for entity in _enemy_entities(previous_state)}
        for entity in _enemy_entities(current_state):
            if entity.entity_id in previous_enemy_ids:
                continue
            events.append(
                SemanticEvent(
                    event_id=f"enemy_seen:{entity.entity_id}:{step}",
                    event_type="enemy_seen",
                    step=step,
                    location=entity.position,
                    importance=0.7,
                    summary=f"Enemy {entity.entity_id} became visible.",
                    evidence=[
                        f"team={entity.attributes.get('team', 'unknown')}",
                        f"role={entity.attributes.get('role', 'unknown')}",
                    ],
                )
            )

        previous_visible_ids = {entity.entity_id for entity in previous_state.visible_entities}
        for entity in current_state.visible_entities:
            if entity.entity_id in previous_visible_ids:
                continue
            if entity.entity_type.endswith("_extractor"):
                events.append(
                    SemanticEvent(
                        event_id=f"extractor_seen:{entity.entity_id}:{step}",
                        event_type="extractor_seen",
                        step=step,
                        location=entity.position,
                        importance=0.6,
                        summary=f"Extractor {entity.entity_id} became visible.",
                        evidence=[f"type={entity.entity_type}"],
                    )
                )
            if entity.entity_type == "junction" and entity.attributes.get("owner") == "neutral":
                events.append(
                    SemanticEvent(
                        event_id=f"neutral_junction_seen:{entity.entity_id}:{step}",
                        event_type="neutral_junction_seen",
                        step=step,
                        location=entity.position,
                        importance=0.6,
                        summary=f"Neutral junction {entity.entity_id} became visible.",
                        evidence=[f"owner={entity.attributes.get('owner', 'unknown')}"],
                    )
                )

        previous_junctions = {
            entity.entity_id: entity for entity in previous_state.visible_entities if entity.entity_type == "junction"
        }
        for entity in current_state.visible_entities:
            if entity.entity_type != "junction":
                continue
            if entity.entity_id not in previous_junctions:
                continue
            previous_owner = str(previous_junctions[entity.entity_id].attributes["owner"])
            current_owner = str(entity.attributes["owner"])
            if previous_owner == current_owner:
                continue
            events.append(
                SemanticEvent(
                    event_id=f"junction_owner_changed:{entity.entity_id}:{step}",
                    event_type="junction_owner_changed",
                    step=step,
                    location=entity.position,
                    importance=0.8,
                    summary=f"Junction ownership changed from {previous_owner} to {current_owner}.",
                    evidence=[f"previous_owner={previous_owner}", f"current_owner={current_owner}"],
                )
            )
        return events


def _enemy_entities(state: MettagridState) -> list[SemanticEntity]:
    if state.team_summary is None:
        return []
    return [
        entity
        for entity in state.visible_entities
        if entity.entity_type == "agent" and entity.attributes.get("team") != state.team_summary.team_id
    ]


def _heart_count(state: MettagridState) -> int:
    if "heart" not in state.self_state.inventory:
        return 0
    return state.self_state.inventory["heart"]


def _inventory_count(state: MettagridState, item: str) -> int:
    if item not in state.self_state.inventory:
        return 0
    return int(state.self_state.inventory[item])
