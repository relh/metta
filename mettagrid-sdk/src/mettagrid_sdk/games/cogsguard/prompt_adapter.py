from __future__ import annotations

from mettagrid_sdk.sdk import MettagridState

_COGSGUARD_SKILLS = (
    (
        "resource_coverage",
        "Mine missing elements, then deposit before overcarrying. "
        "resource_bias only prefers a resource type; it does not hard-lock one extractor.",
    ),
    (
        "focused_extractor_lock",
        "When one exact extractor is productive or oscillation is detected, "
        "set target_entity_id to pin that extractor until facts change.",
    ),
    (
        "region_reanchor",
        "Use target_region for west/east/frontier steering when you want lane pressure "
        "or exploration without pinning one entity yet.",
    ),
    (
        "heart_gated_alignment",
        "Aligners and scramblers should secure a heart before committing to junction pressure.",
    ),
    ("safe_deposit_cycle", "If carrying payload under pressure or low HP, route back toward a friendly hub."),
    ("lane_pressure", "Once hearts are online, convert spare pressure into aligner or scrambler lane control."),
)

_COGSGUARD_BEST_PRACTICES = (
    "Prefer one strong steering primitive at a time: target_entity_id first, then target_region, then resource_bias.",
    (
        'Use sdk.helpers.nearest_visible_entity(entity_type="junction", label="neutral") '
        "to choose one decisive focus target."
    ),
    (
        'Use sdk.helpers.visible_entities(entity_type="junction", label="enemy") '
        "to inspect lane pressure without pinning one id yet."
    ),
    (
        "Use sdk.helpers.shared_inventory() and sdk.helpers.recent_event_types() "
        "as progress signals before escalating phases or rewriting plans."
    ),
    (
        "Keep step(sdk) short and strategic; let the semantic baseline handle movement, mining, "
        "deposits, and junction actions."
    ),
    "If a target stops being productive, change directive fields or phase instead of layering more timeout ladders.",
)


class CogsguardPromptAdapter:
    def render_state(self, state: MettagridState) -> str:
        self_state = state.self_state
        inventory_text = _format_mapping(self_state.inventory)
        status_text = ", ".join(self_state.status) if self_state.status else "none"
        team_id = "unknown" if state.team_summary is None else state.team_summary.team_id
        lines = [
            "SELF",
            f"step: {state.step}",
            f"team: {team_id}",
            f"role: {self_state.role}",
            f"position: ({self_state.position.x}, {self_state.position.y})",
            f"inventory: {inventory_text}",
            f"status: {status_text}",
            f"shared_inventory: {self._shared_inventory_text(state)}",
            f"shared_objectives: {self._shared_objectives_text(state)}",
            "VISIBLE",
        ]
        for entity in state.visible_entities:
            attribute_text = _format_mapping(entity.attributes)
            label_text = ", ".join(entity.labels)
            lines.append(
                f"- {entity.entity_type} at ({entity.position.x}, {entity.position.y}) [{label_text}] {attribute_text}"
            )
        if state.recent_events:
            lines.append("RECENT_EVENTS")
            for event in state.recent_events:
                lines.append(f"- {event.event_type}: {event.summary}")
        return "\n".join(lines)

    def render_skill_library(self) -> str:
        return "\n".join(
            [
                "SKILLS",
                *(f"- {name}: {description}" for name, description in _COGSGUARD_SKILLS),
                "CONTROL_PRIMITIVES",
                "- role: choose miner, aligner, or scrambler to switch the semantic baseline behavior family",
                "- objective: choose resource_coverage, economy_bootstrap, or aligner_pressure for the current phase",
                "- target_entity_id: strongest focus primitive; use it for one exact extractor, junction, "
                "or visible entity",
                "- target_region: broader lane or region bias when you do not want to pin one exact entity yet",
                "- resource_bias: resource-type preference among viable extractors; not a hard lock on one extractor",
                "BEST_PRACTICES",
                *(f"- {line}" for line in _COGSGUARD_BEST_PRACTICES),
            ]
        )

    def _shared_inventory_text(self, state: MettagridState) -> str:
        if state.team_summary is None:
            return "none"
        return _format_mapping(state.team_summary.shared_inventory)

    def _shared_objectives_text(self, state: MettagridState) -> str:
        if state.team_summary is None or not state.team_summary.shared_objectives:
            return "none"
        return ", ".join(state.team_summary.shared_objectives)


def _format_mapping(values: dict[str, str | int | float | bool]) -> str:
    if not values:
        return "none"
    return ", ".join(f"{key}={values[key]}" for key in sorted(values))
