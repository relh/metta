"""
Debug visualization and logging system for the Cogas agent.

Provides structured, per-tick debug output for diagnosing junction control
performance. Output is parseable by eval harness scripts (eval_cogas.sh,
enrich_eval_output.py).

Verbosity levels (set via URI param ``cogas?debug=0/1/2``):
    0 — disabled (default)
    1 — per-tick summary: junction counts + score estimate
    2 — full detail: per-agent role/target/action/position + role history

All output lines are prefixed with ``[cogas:debug]`` so they can be grepped
from mixed stdout without interfering with the existing ``[cogas]`` trace
lines or the JSON eval output.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Per-agent tick record
# ---------------------------------------------------------------------------


@dataclass
class AgentTickRecord:
    """Snapshot of one agent's state for a single tick."""

    agent_id: int
    role: str
    position: tuple[int, int]
    action: str
    target: Optional[tuple[int, int]] = None
    phase: str = ""
    hp: int = 0
    energy: int = 0


# ---------------------------------------------------------------------------
# Junction status snapshot
# ---------------------------------------------------------------------------


@dataclass
class JunctionSnapshot:
    """Aggregated junction alignment counts for a single tick."""

    aligned: int = 0  # cogs-controlled
    enemy: int = 0  # clips-controlled
    neutral: int = 0  # unaligned
    total: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "aligned": self.aligned,
            "enemy": self.enemy,
            "neutral": self.neutral,
            "total": self.total,
        }


# ---------------------------------------------------------------------------
# Score estimation tracker
# ---------------------------------------------------------------------------


@dataclass
class ScoreEstimate:
    """Tracks an estimated score value over time."""

    history: list[tuple[int, float]] = field(default_factory=list)

    def record(self, step: int, value: float) -> None:
        self.history.append((step, value))

    def latest(self) -> Optional[float]:
        return self.history[-1][1] if self.history else None

    def trend(self, window: int = 10) -> Optional[float]:
        """Return average change per step over the last *window* entries."""
        if len(self.history) < 2:
            return None
        recent = self.history[-window:]
        if len(recent) < 2:
            return None
        delta = recent[-1][1] - recent[0][1]
        steps = recent[-1][0] - recent[0][0]
        return delta / steps if steps else None


# ---------------------------------------------------------------------------
# Role assignment history
# ---------------------------------------------------------------------------


@dataclass
class RoleEvent:
    """One role-change event."""

    step: int
    agent_id: int
    old_role: str
    new_role: str


# ---------------------------------------------------------------------------
# DebugLogger — the main interface
# ---------------------------------------------------------------------------


class DebugLogger:
    """Collects and emits structured debug output each tick.

    Instantiated once per ``CogasPolicy`` when ``debug >= 1``.  Each tick,
    ``CogasBrain.step_with_state`` calls :meth:`record_agent_tick` and the
    policy's ``step_batch`` calls :meth:`flush_tick` at the end of the batch.

    Parameters
    ----------
    level : int
        Verbosity level (1 or 2).
    num_agents : int
        Total number of agents managed by the policy.
    output : file-like, optional
        Where to write output. Defaults to ``sys.stderr`` so it doesn't
        pollute the JSON eval output on stdout.
    """

    PREFIX = "[cogas:debug]"

    def __init__(
        self,
        level: int = 1,
        num_agents: int = 0,
        output: Any = None,
    ) -> None:
        self.level = level
        self.num_agents = num_agents
        self._out = output or sys.stderr

        # Per-tick accumulator — cleared on flush
        self._tick_records: list[AgentTickRecord] = []
        self._current_step: int = 0

        # Persistent trackers
        self._junction_history: list[tuple[int, JunctionSnapshot]] = []
        self._score_estimate = ScoreEstimate()
        self._role_events: list[RoleEvent] = []
        self._last_roles: dict[int, str] = {}

    # ------------------------------------------------------------------
    # Recording (called per agent per tick)
    # ------------------------------------------------------------------

    def record_agent_tick(
        self,
        agent_id: int,
        role: str,
        position: tuple[int, int],
        action: str,
        target: Optional[tuple[int, int]] = None,
        phase: str = "",
        hp: int = 0,
        energy: int = 0,
        step: int = 0,
    ) -> None:
        """Record a single agent's tick data."""
        self._current_step = max(self._current_step, step)
        self._tick_records.append(
            AgentTickRecord(
                agent_id=agent_id,
                role=role,
                position=position,
                action=action,
                target=target,
                phase=phase,
                hp=hp,
                energy=energy,
            )
        )

        # Track role changes
        prev_role = self._last_roles.get(agent_id)
        if prev_role is not None and prev_role != role:
            self._role_events.append(RoleEvent(step=step, agent_id=agent_id, old_role=prev_role, new_role=role))
        self._last_roles[agent_id] = role

    def record_junction_status(
        self,
        aligned: int,
        enemy: int,
        neutral: int,
        step: int,
    ) -> None:
        """Record junction alignment counts for this tick."""
        snap = JunctionSnapshot(
            aligned=aligned,
            enemy=enemy,
            neutral=neutral,
            total=aligned + enemy + neutral,
        )
        self._junction_history.append((step, snap))

    def record_score_estimate(self, step: int, value: float) -> None:
        """Record an estimated score value (e.g. aligned.junction.held proxy)."""
        self._score_estimate.record(step, value)

    # ------------------------------------------------------------------
    # Flush (called once per tick after all agents stepped)
    # ------------------------------------------------------------------

    def flush_tick(self) -> None:
        """Emit debug output for the current tick and reset accumulators."""
        step = self._current_step
        if not self._tick_records and not self._junction_history:
            return

        # --- Level 1: junction summary + score ---
        jsnap = self._junction_history[-1][1] if self._junction_history else None
        score_val = self._score_estimate.latest()
        score_trend = self._score_estimate.trend()

        summary_parts: list[str] = [f"t={step}"]
        if jsnap:
            summary_parts.append(f"junc(a={jsnap.aligned} e={jsnap.enemy} n={jsnap.neutral})")
        if score_val is not None:
            trend_str = ""
            if score_trend is not None:
                sign = "+" if score_trend >= 0 else ""
                trend_str = f" {sign}{score_trend:.1f}/t"
            summary_parts.append(f"score~{score_val:.0f}{trend_str}")

        self._emit(" ".join(summary_parts))

        # --- Level 2: per-agent detail + role history ---
        if self.level >= 2:
            for rec in sorted(self._tick_records, key=lambda r: r.agent_id):
                tgt = f" tgt={rec.target}" if rec.target else ""
                self._emit(
                    f"  a={rec.agent_id} {rec.role} "
                    f"({rec.position[0]},{rec.position[1]}) "
                    f"hp={rec.hp} e={rec.energy} "
                    f"ph={rec.phase} "
                    f"act={rec.action}{tgt}"
                )

            # Emit any role changes that happened this tick
            tick_role_events = [e for e in self._role_events if e.step == step]
            for ev in tick_role_events:
                self._emit(f"  role_change a={ev.agent_id} {ev.old_role}->{ev.new_role}")

        # Reset per-tick accumulator
        self._tick_records.clear()

    # ------------------------------------------------------------------
    # End-of-episode summary (parseable by eval harness)
    # ------------------------------------------------------------------

    def emit_episode_summary(self, episode: int) -> None:
        """Emit a structured JSON summary at the end of an episode.

        This is the primary output consumed by eval harness scripts.
        Format: one JSON object per line, prefixed with ``[cogas:debug:summary]``.
        """
        junc_timeline = [{"step": s, **snap.as_dict()} for s, snap in self._junction_history]

        score_timeline = [{"step": s, "value": round(v, 2)} for s, v in self._score_estimate.history]

        role_changes = [
            {
                "step": ev.step,
                "agent_id": ev.agent_id,
                "old_role": ev.old_role,
                "new_role": ev.new_role,
            }
            for ev in self._role_events
        ]

        summary = {
            "episode": episode,
            "total_steps": self._current_step,
            "junction_timeline": junc_timeline,
            "score_timeline": score_timeline,
            "role_changes": role_changes,
            "final_roles": dict(sorted(self._last_roles.items())),
        }

        line = json.dumps(summary, separators=(",", ":"))
        print(f"[cogas:debug:summary] {line}", file=self._out, flush=True)

    def reset_episode(self) -> None:
        """Reset state between episodes."""
        self._tick_records.clear()
        self._junction_history.clear()
        self._score_estimate = ScoreEstimate()
        self._role_events.clear()
        self._last_roles.clear()
        self._current_step = 0

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _emit(self, msg: str) -> None:
        print(f"{self.PREFIX} {msg}", file=self._out, flush=True)
