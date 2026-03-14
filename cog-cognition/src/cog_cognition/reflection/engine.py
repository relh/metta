from __future__ import annotations

from collections import defaultdict

from cog_cyborg.memory.store import MemoryStore
from mettagrid_sdk.sdk import BeliefMemoryRecord, EventMemoryRecord, MemoryRecord, MettagridState

from cog_cognition.reflection.models import TacticalBelief

_DEFAULT_MIN_IMPORTANCE = 0.6
_DEFAULT_MIN_EVENT_COUNT = 2
_RECENT_BELIEF_WINDOW = 30
_REGION_SUFFIXES = ("_lane", "_region")


class ReflectionEngine:
    def __init__(
        self,
        *,
        min_importance: float = _DEFAULT_MIN_IMPORTANCE,
        min_event_count: int = _DEFAULT_MIN_EVENT_COUNT,
        recent_limit: int = 24,
    ) -> None:
        self._min_importance = min_importance
        self._min_event_count = min_event_count
        self._recent_limit = recent_limit

    def reflect(self, state: MettagridState, memory: MemoryStore) -> list[BeliefMemoryRecord]:
        recent_records = memory.recent_records(limit=self._recent_limit)
        event_records = [record for record in recent_records if isinstance(record, EventMemoryRecord)]
        beliefs = self._synthesize_beliefs(state, event_records)

        created_records = []
        for index, belief in enumerate(beliefs, start=1):
            if _has_recent_duplicate(recent_records, belief, state):
                continue
            created_records.append(
                memory.append_belief(
                    record_id=f"belief:{belief.belief_type}:{state.step}:{index}",
                    belief_type=belief.belief_type,
                    summary=belief.summary,
                    game=state.game,
                    step=state.step,
                    role_context=belief.role_context,
                    tags=belief.tags,
                    importance=belief.importance,
                    confidence=belief.confidence,
                    source="reflection",
                    evidence_ids=belief.evidence_ids,
                    location=belief.location,
                    region_id=belief.region_id,
                )
            )
        return created_records

    def _synthesize_beliefs(
        self,
        state: MettagridState,
        event_records: list[EventMemoryRecord],
    ) -> list[TacticalBelief]:
        beliefs = []
        beliefs.extend(_lane_contested_beliefs(state, event_records, self._min_importance, self._min_event_count))
        beliefs.extend(_region_path_risky_beliefs(state, event_records, self._min_importance, self._min_event_count))
        beliefs.extend(
            _aligner_requires_heart_beliefs(state, event_records, self._min_importance, self._min_event_count)
        )
        return beliefs


def _lane_contested_beliefs(
    state: MettagridState,
    event_records: list[EventMemoryRecord],
    min_importance: float,
    min_event_count: int,
) -> list[TacticalBelief]:
    grouped_events = defaultdict(list)
    for record in event_records:
        if record.event_type not in {"enemy_seen", "junction_owner_changed", "region_unsafe"}:
            continue
        if record.importance < min_importance:
            continue
        region_key = _region_key(record)
        if region_key is None:
            continue
        grouped_events[region_key].append(record)

    beliefs = []
    for region_key, grouped in grouped_events.items():
        if len(grouped) < min_event_count:
            continue
        evidence_ids = [record.record_id for record in grouped]
        avg_importance = sum(record.importance for record in grouped) / len(grouped)
        confidence = min(0.95, round(0.45 + 0.15 * len(grouped) + 0.2 * avg_importance, 2))
        beliefs.append(
            TacticalBelief(
                belief_type="lane_contested",
                summary=f"{region_key} is contested after repeated enemy pressure and ownership churn.",
                confidence=confidence,
                evidence_ids=evidence_ids,
                tags=sorted({state.self_state.role or "unknown", region_key, "contest", "enemy", "junction"}),
                role_context=state.self_state.role,
                importance=min(1.0, round(avg_importance, 2)),
                region_id=region_key,
                location=grouped[-1].location,
            )
        )
    return beliefs


def _region_path_risky_beliefs(
    state: MettagridState,
    event_records: list[EventMemoryRecord],
    min_importance: float,
    min_event_count: int,
) -> list[TacticalBelief]:
    grouped_events = defaultdict(list)
    for record in event_records:
        if record.event_type not in {"path_blocked", "region_unsafe", "junction_not_reachable"}:
            continue
        if record.importance < min_importance:
            continue
        region_key = _region_key(record)
        if region_key is None:
            continue
        grouped_events[region_key].append(record)

    beliefs = []
    for region_key, grouped in grouped_events.items():
        if len(grouped) < min_event_count:
            continue
        evidence_ids = [record.record_id for record in grouped]
        avg_importance = sum(record.importance for record in grouped) / len(grouped)
        confidence = min(0.95, round(0.4 + 0.15 * len(grouped) + 0.2 * avg_importance, 2))
        beliefs.append(
            TacticalBelief(
                belief_type="region_path_risky",
                summary=f"{region_key} pathing is risky after repeated blocked or unsafe movement signals.",
                confidence=confidence,
                evidence_ids=evidence_ids,
                tags=sorted({state.self_state.role or "unknown", region_key, "path", "risky", "unsafe"}),
                role_context=state.self_state.role,
                importance=min(1.0, round(avg_importance, 2)),
                region_id=region_key,
                location=grouped[-1].location,
            )
        )
    return beliefs


def _aligner_requires_heart_beliefs(
    state: MettagridState,
    event_records: list[EventMemoryRecord],
    min_importance: float,
    min_event_count: int,
) -> list[TacticalBelief]:
    grouped = [
        record
        for record in event_records
        if record.event_type == "capture_failed_no_heart"
        and record.importance >= min_importance
        and record.role_context == "aligner"
    ]
    if len(grouped) < min_event_count:
        return []

    avg_importance = sum(record.importance for record in grouped) / len(grouped)
    confidence = min(0.98, round(0.5 + 0.1 * len(grouped) + 0.2 * avg_importance, 2))
    return [
        TacticalBelief(
            belief_type="aligner_requires_heart_before_commit",
            summary="Aligners should secure a heart before committing to neutral junction pressure.",
            confidence=confidence,
            evidence_ids=[record.record_id for record in grouped],
            tags=["aligner", "heart", "junction"],
            role_context="aligner",
            importance=min(1.0, round(avg_importance, 2)),
            location=grouped[-1].location,
        )
    ]


def _region_key(record: EventMemoryRecord) -> str | None:
    region_tags = [tag for tag in record.tags if tag.endswith(_REGION_SUFFIXES)]
    if region_tags:
        return region_tags[0]
    if record.region_id is not None:
        return record.region_id
    if record.location is None:
        return None
    return f"region@{record.location.x},{record.location.y}"


def _has_recent_duplicate(
    recent_records: list[MemoryRecord],
    belief: TacticalBelief,
    state: MettagridState,
) -> bool:
    for record in recent_records:
        if not isinstance(record, BeliefMemoryRecord):
            continue
        if record.belief_type != belief.belief_type:
            continue
        if record.role_context != belief.role_context:
            continue
        if record.region_id != belief.region_id:
            continue
        if record.step is None or state.step is None:
            return True
        if state.step - record.step <= _RECENT_BELIEF_WINDOW:
            return True
    return False
