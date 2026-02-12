"""Dashboard computation logic for policy performance analysis.

Ported from skills/cg.policy-dashboard/generate.py — pure functions only, no I/O.
"""

from __future__ import annotations

import json
import statistics
from typing import Any

from pydantic import BaseModel

# === Pydantic Models ===


class DashboardEpisode(BaseModel):
    """Episode data for dashboard computation."""

    episode_id: str
    job_id: str
    opponent_name: str
    opponent_version: int
    team_composition: str  # "6v2", "4v4", "2v6"
    reward: float
    status: str  # "completed", "failed"
    error_type: str | None = None
    steps: int = 0
    metrics: dict[str, Any] = {}


class DerivedMetrics(BaseModel):
    """Computed KPIs derived from episode metrics."""

    # Efficiency KPIs (0-1 scale)
    move_efficiency: float = 0.0
    action_success_rate: float = 0.0
    vibe_change_rate: float = 0.0

    # Resource KPIs
    resource_retention: float = 0.0

    # Vulnerability KPIs
    freeze_vulnerability: float = 0.0

    # Junction KPIs
    junction_control_rate: float = 0.0
    alignment_stability: float = 0.0
    net_alignment_rate: float = 0.0

    # Reward KPIs
    avg_reward: float = 0.0

    # Additional KPIs
    noop_rate: float = 0.0
    resource_efficiency_per_step: float = 0.0
    hearts_to_junction_rate: float = 0.0
    reward_consistency: float = 0.0
    reward_nonzero_pct: float = 0.0

    # Strategy profile scores (0-100)
    profile_aggressive: float = 0.0
    profile_defensive: float = 0.0
    profile_resource_hoarder: float = 0.0
    profile_junction_hunter: float = 0.0
    profile_mobile_scout: float = 0.0

    # Diagnostic flags
    diagnostics: list[str] = []


class OpponentStats(BaseModel):
    """Per-opponent metric aggregation."""

    count: int
    total_reward: float
    avg_reward: float
    avg_metrics: dict[str, float]
    strategy_profile: dict[str, float]


class TeamCompStats(BaseModel):
    """Per-composition KPI breakdown."""

    composition: str
    count: int
    avg_reward: float
    avg_move_efficiency: float
    avg_junction_aligned: float
    avg_resource_gained: float


class PolicyInfo(BaseModel):
    """Policy metadata for dashboard response."""

    id: str
    name: str
    version: int
    rank: int | None = None
    score: float | None = None
    matches: int = 0


class DashboardDerived(BaseModel):
    """Derived analytics returned in the dashboard response."""

    kpis: DerivedMetrics
    team_comp: list[TeamCompStats]
    opponent_metrics: dict[str, OpponentStats]


class DashboardResponse(BaseModel):
    """Full dashboard response returned by the API."""

    policy: PolicyInfo
    episodes: list[DashboardEpisode]
    season: str
    generated_at: str
    derived: DashboardDerived


# === Pure computation functions ===

RESOURCES = ["carbon", "heart", "oxygen", "silicon", "germanium"]


def _safe_div(a: float, b: float, default: float = 0.0) -> float:
    return a / b if b > 0 else default


def compute_derived_metrics(episodes: list[DashboardEpisode]) -> DerivedMetrics:
    """Compute policy-level KPIs from episode metrics."""
    if not episodes:
        return DerivedMetrics()

    totals: dict[str, float] = {}
    total_steps = 0
    completed = [e for e in episodes if e.status == "completed"]

    for ep in completed:
        total_steps += ep.steps
        for key, value in ep.metrics.items():
            if isinstance(value, (int, float)):
                totals[key] = totals.get(key, 0) + value

    n_episodes = len(completed) or 1

    def get(key: str, default: float = 0.0) -> float:
        return totals.get(key, default)

    # Efficiency KPIs
    move_success = get("action.move.success")
    move_failed = get("action.move.failed")
    move_efficiency = _safe_div(move_success, move_success + move_failed)

    action_failed = get("action.failed")
    total_actions = sum(v for k, v in totals.items() if k.startswith("action.") and ".success" in k)
    total_actions += action_failed
    action_success_rate = _safe_div(total_actions - action_failed, total_actions)

    vibe_change_success = get("action.change_vibe.success")
    vibe_change_rate = _safe_div(vibe_change_success, total_actions)

    # Resource KPIs
    total_amount = sum(get(f"{r}.amount") for r in RESOURCES)
    total_gained = sum(get(f"{r}.gained") for r in RESOURCES)
    resource_retention = _safe_div(total_amount, total_gained)

    # Vulnerability KPIs
    frozen_ticks = get("status.frozen.ticks")
    freeze_vulnerability = _safe_div(frozen_ticks, total_steps) if total_steps > 0 else 0.0

    # Junction KPIs
    junction_aligned = get("junction.aligned_by_agent")
    junction_scrambled = get("junction.scrambled_by_agent")
    junction_total = junction_aligned + junction_scrambled
    junction_control_rate = _safe_div(junction_aligned, junction_total)

    aligned_gained = get("aligned.junction.gained", junction_aligned)
    aligned_lost = get("aligned.junction.lost")
    aligned_held = get("aligned.junction.held")
    alignment_stability = _safe_div(aligned_held, aligned_gained) if aligned_gained > 0 else 0.0
    net_alignment_rate = _safe_div(aligned_gained - aligned_lost, aligned_gained)

    # Strategy profiles (0-100)
    profile_aggressive = min(100, (junction_scrambled / n_episodes) * 10 + (vibe_change_success / n_episodes) * 5)

    noop_count = get("action.noop.success")
    move_rate = _safe_div(move_success, move_success + noop_count)
    profile_defensive = min(100, (noop_count / n_episodes / 10) + (1 - move_rate) * 50)

    profile_resource_hoarder = min(100, resource_retention * 50 + (total_amount / n_episodes / 10))

    profile_junction_hunter = min(100, (junction_aligned / n_episodes) * 3 + junction_control_rate * 50)

    noop_rate_profile = _safe_div(noop_count, move_success + noop_count)
    profile_mobile_scout = min(100, move_efficiency * 50 + (1 - noop_rate_profile) * 50)

    # Additional KPIs
    noop_rate = _safe_div(noop_count, total_actions)
    resource_efficiency_per_step = _safe_div(total_gained, total_steps) if total_steps > 0 else 0.0

    heart_lost = get("heart.lost")
    hearts_to_junction_rate = _safe_div(junction_aligned, heart_lost)

    rewards = [e.reward for e in completed]
    if len(rewards) >= 2:
        mean_reward = statistics.mean(rewards)
        std_reward = statistics.stdev(rewards)
        reward_consistency = max(0.0, min(1.0, 1.0 - (std_reward / mean_reward))) if mean_reward > 0 else 0.0
    else:
        reward_consistency = 0.0

    avg_reward = _safe_div(sum(rewards), len(rewards))
    nonzero_count = sum(1 for r in rewards if r > 0.1)
    reward_nonzero_pct = _safe_div(nonzero_count, len(rewards))

    # Diagnostics
    diagnostics = compute_diagnostics(
        episodes,
        completed,
        totals,
        total_steps,
        n_episodes,
        move_efficiency,
        move_failed,
        freeze_vulnerability,
        junction_aligned,
        vibe_change_success,
        noop_rate,
        noop_count,
        rewards,
    )

    return DerivedMetrics(
        move_efficiency=move_efficiency,
        action_success_rate=action_success_rate,
        vibe_change_rate=vibe_change_rate,
        resource_retention=resource_retention,
        freeze_vulnerability=freeze_vulnerability,
        junction_control_rate=junction_control_rate,
        alignment_stability=alignment_stability,
        net_alignment_rate=net_alignment_rate,
        avg_reward=avg_reward,
        noop_rate=noop_rate,
        resource_efficiency_per_step=resource_efficiency_per_step,
        hearts_to_junction_rate=hearts_to_junction_rate,
        reward_consistency=reward_consistency,
        reward_nonzero_pct=reward_nonzero_pct,
        profile_aggressive=profile_aggressive,
        profile_defensive=profile_defensive,
        profile_resource_hoarder=profile_resource_hoarder,
        profile_junction_hunter=profile_junction_hunter,
        profile_mobile_scout=profile_mobile_scout,
        diagnostics=diagnostics,
    )


def compute_diagnostics(
    episodes: list[DashboardEpisode],
    completed: list[DashboardEpisode],
    totals: dict[str, float],
    total_steps: int,
    n_episodes: int,
    move_efficiency: float,
    move_failed: float,
    freeze_vulnerability: float,
    junction_aligned: float,
    vibe_change_success: float,
    noop_rate: float,
    noop_count: float,
    rewards: list[float],
) -> list[str]:
    """Compute diagnostic strings from aggregated metrics."""
    diagnostics: list[str] = []

    def get(key: str, default: float = 0.0) -> float:
        return totals.get(key, default)

    if move_efficiency < 0.7 and move_failed > n_episodes * 10:
        diagnostics.append("High movement failures - check pathfinding or obstacle handling")

    action_timeout = get("action.timeout")
    if action_timeout > n_episodes * 5:
        timeout_per_ep = action_timeout / n_episodes
        diagnostics.append(f"Action timeouts detected ({timeout_per_ep:.1f}/ep) - policy may have latency issues")

    if freeze_vulnerability > 0.1:
        diagnostics.append(f"Spending {freeze_vulnerability * 100:.1f}% of time frozen - improve combat avoidance")

    heart_gained = get("heart.gained")
    if junction_aligned < n_episodes * 2 and heart_gained > n_episodes * 3:
        diagnostics.append("Hearts collected but low junction alignment - check aligner activation")

    if vibe_change_success == 0 and n_episodes >= 5:
        diagnostics.append("No vibe changes detected - policy may not be using change_vibe action")

    total_lost = sum(get(f"{r}.lost") for r in RESOURCES)
    total_gained = sum(get(f"{r}.gained") for r in RESOURCES)
    if total_lost > total_gained * 0.5:
        diagnostics.append("High resource loss - resources being lost faster than gained")

    avg_steps = total_steps / n_episodes if n_episodes > 0 else 0
    short_episodes = sum(1 for e in completed if e.steps < avg_steps * 0.5)
    if short_episodes > n_episodes * 0.2:
        diagnostics.append(f"{short_episodes} episodes terminated early - possible stability issues")

    if noop_rate > 0.15 and noop_count > n_episodes * 100:
        diagnostics.append(f"High noop rate ({noop_rate * 100:.1f}%) - policy may be indecisive or stuck")

    # Matchup disparity
    by_opponent: dict[str, list[float]] = {}
    for e in completed:
        by_opponent.setdefault(e.opponent_name, []).append(e.reward)
    opponent_avgs = {opp: sum(rs) / len(rs) for opp, rs in by_opponent.items() if len(rs) >= 3}
    if opponent_avgs:
        best_avg = max(opponent_avgs.values())
        worst_avg = min(opponent_avgs.values())
        if best_avg > 2.0 and worst_avg < 0.5:
            best_opp = max(opponent_avgs, key=opponent_avgs.get)  # type: ignore[arg-type]
            worst_opp = min(opponent_avgs, key=opponent_avgs.get)  # type: ignore[arg-type]
            diagnostics.append(
                f"Matchup disparity - best avg {best_avg:.1f} vs {best_opp}, worst avg {worst_avg:.1f} vs {worst_opp}"
            )

    # Declining rewards
    if len(rewards) >= 10:
        n_r = len(rewards)
        x_mean = (n_r - 1) / 2.0
        y_mean = sum(rewards) / n_r
        numerator = sum((i - x_mean) * (rewards[i] - y_mean) for i in range(n_r))
        denominator = sum((i - x_mean) ** 2 for i in range(n_r))
        if denominator > 0:
            slope = numerator / denominator
            if slope < -0.05:
                diagnostics.append(f"Declining rewards (slope={slope:.3f}) - recent episodes scoring worse")

    # High freeze + low reward
    if len(completed) >= 5:
        avg_reward_all = sum(e.reward for e in completed) / n_episodes
        frozen_low_count = sum(
            1
            for e in completed
            if e.steps > 0
            and e.metrics.get("status.frozen.ticks", 0) / e.steps > 0.15
            and e.reward < avg_reward_all * 0.5
        )
        if frozen_low_count > n_episodes * 0.15:
            diagnostics.append(
                f"High freeze time and low reward in {frozen_low_count} episodes "
                f"({frozen_low_count / n_episodes * 100:.0f}%) - check combat avoidance"
            )

    # Team comp red flag
    comp_rewards: dict[str, list[float]] = {}
    for e in completed:
        comp_rewards.setdefault(e.team_composition, []).append(e.reward)
    avg_6v2 = sum(comp_rewards.get("6v2", [0])) / max(len(comp_rewards.get("6v2", [0])), 1)
    avg_2v6 = sum(comp_rewards.get("2v6", [0])) / max(len(comp_rewards.get("2v6", [0])), 1)
    if avg_2v6 > 0 and avg_6v2 / avg_2v6 > 3.0 and len(comp_rewards.get("6v2", [])) >= 3:
        diagnostics.append(
            f"Over-reliance on agent count - 6v2 avg {avg_6v2:.1f} vs 2v6 avg {avg_2v6:.1f} "
            f"(ratio {avg_6v2 / avg_2v6:.1f}x)"
        )

    # Zero-count detection
    capability_metrics = [
        "junction.aligned_by_agent",
        "junction.scrambled_by_agent",
        "action.change_vibe.success",
    ]
    zero_capabilities = []
    for metric in capability_metrics:
        if all(e.metrics.get(metric, 0) == 0 for e in completed):
            zero_capabilities.append(metric)
    if zero_capabilities:
        names = ", ".join(zero_capabilities)
        diagnostics.append(f"Unused capabilities (always zero): {names}")

    return diagnostics


def compute_team_comp_analysis(episodes: list[DashboardEpisode]) -> list[TeamCompStats]:
    """Compute per-composition KPI breakdown."""
    by_comp: dict[str, list[DashboardEpisode]] = {}
    for e in episodes:
        if e.status == "completed":
            by_comp.setdefault(e.team_composition, []).append(e)

    result = []
    for comp, eps in sorted(by_comp.items()):
        n = len(eps)
        avg_reward = sum(e.reward for e in eps) / n

        total_move_success = sum(e.metrics.get("action.move.success", 0) for e in eps)
        total_move_failed = sum(e.metrics.get("action.move.failed", 0) for e in eps)
        total_move = total_move_success + total_move_failed
        move_eff = total_move_success / total_move if total_move > 0 else 0

        avg_junction = sum(e.metrics.get("junction.aligned_by_agent", 0) for e in eps) / n
        avg_resource = sum(sum(e.metrics.get(f"{r}.gained", 0) for r in RESOURCES) for e in eps) / n

        result.append(
            TeamCompStats(
                composition=comp,
                count=n,
                avg_reward=round(avg_reward, 4),
                avg_move_efficiency=round(move_eff, 4),
                avg_junction_aligned=round(avg_junction, 4),
                avg_resource_gained=round(avg_resource, 4),
            )
        )

    return result


def compute_opponent_metrics(episodes: list[DashboardEpisode]) -> dict[str, OpponentStats]:
    """Pre-compute per-opponent metric aggregation."""
    by_opponent: dict[str, list[DashboardEpisode]] = {}
    for e in episodes:
        if e.status == "completed":
            by_opponent.setdefault(e.opponent_name, []).append(e)

    result: dict[str, OpponentStats] = {}
    for opp, eps in by_opponent.items():
        n = len(eps)
        total_reward = sum(e.reward for e in eps)
        avg_reward = total_reward / n
        summed_metrics: dict[str, float] = {}
        for e in eps:
            for k, v in e.metrics.items():
                if isinstance(v, (int, float)):
                    summed_metrics[k] = summed_metrics.get(k, 0) + v

        avg_metrics = {k: v / n for k, v in summed_metrics.items()}

        m = avg_metrics
        move_s = m.get("action.move.success", 0)
        move_f = m.get("action.move.failed", 0)
        noop = m.get("action.noop.success", 0)
        vibe = m.get("action.change_vibe.success", 0)
        j_aligned = m.get("junction.aligned_by_agent", 0)
        j_scrambled = m.get("junction.scrambled_by_agent", 0)
        j_total = j_aligned + j_scrambled
        total_amount = sum(m.get(f"{r}.amount", 0) for r in RESOURCES)
        total_gained_r = sum(m.get(f"{r}.gained", 0) for r in RESOURCES)
        resource_retention = total_amount / total_gained_r if total_gained_r > 0 else 0
        move_eff = move_s / (move_s + move_f) if (move_s + move_f) > 0 else 0
        j_control = j_aligned / j_total if j_total > 0 else 0
        move_rate = move_s / (move_s + noop) if (move_s + noop) > 0 else 0
        noop_rate_p = noop / (move_s + noop) if (move_s + noop) > 0 else 0

        result[opp] = OpponentStats(
            count=n,
            total_reward=round(total_reward, 4),
            avg_reward=round(avg_reward, 4),
            avg_metrics={k: round(v, 4) for k, v in avg_metrics.items()},
            strategy_profile={
                "aggressive": round(min(100, j_scrambled * 10 + vibe * 5), 2),
                "defensive": round(min(100, noop / 10 + (1 - move_rate) * 50), 2),
                "resource_hoarder": round(min(100, resource_retention * 50 + total_amount / 10), 2),
                "junction_hunter": round(min(100, j_aligned * 3 + j_control * 50), 2),
                "mobile_scout": round(min(100, move_eff * 50 + (1 - noop_rate_p) * 50), 2),
            },
        )

    return result


# === Claude analysis helpers ===


def build_analysis_summary(
    policy_info: PolicyInfo,
    episodes: list[DashboardEpisode],
    derived: DerivedMetrics,
    season: str,
) -> dict[str, Any]:
    """Build compact summary of derived metrics for Claude analysis."""
    completed = [e for e in episodes if e.status == "completed"]
    rewards = [e.reward for e in completed]

    # Per-opponent summary
    by_opponent: dict[str, list[DashboardEpisode]] = {}
    for e in completed:
        by_opponent.setdefault(e.opponent_name, []).append(e)

    opponent_summary = {}
    for opp, eps in by_opponent.items():
        opp_rewards = [e.reward for e in eps]
        avg_m: dict[str, float] = {}
        for e in eps:
            for k, v in e.metrics.items():
                if isinstance(v, (int, float)):
                    avg_m[k] = avg_m.get(k, 0) + v
        n = len(eps)
        avg_m = {k: v / n for k, v in avg_m.items()}

        move_s = avg_m.get("action.move.success", 0)
        move_f = avg_m.get("action.move.failed", 0)
        noop = avg_m.get("action.noop.success", 0)
        vibe = avg_m.get("action.change_vibe.success", 0)
        j_aligned = avg_m.get("junction.aligned_by_agent", 0)
        j_scrambled = avg_m.get("junction.scrambled_by_agent", 0)
        j_total = j_aligned + j_scrambled
        move_rate = move_s / (move_s + noop) if (move_s + noop) > 0 else 0
        noop_rate_p = noop / (move_s + noop) if (move_s + noop) > 0 else 0
        move_eff = move_s / (move_s + move_f) if (move_s + move_f) > 0 else 0
        j_control = j_aligned / j_total if j_total > 0 else 0

        opponent_summary[opp] = {
            "count": n,
            "avg_reward": round(sum(opp_rewards) / n, 4),
            "strategy_profile": {
                "aggressive": round(min(100, j_scrambled * 10 + vibe * 5), 2),
                "defensive": round(min(100, noop / 10 + (1 - move_rate) * 50), 2),
                "junction_hunter": round(min(100, j_aligned * 3 + j_control * 50), 2),
                "mobile_scout": round(min(100, move_eff * 50 + (1 - noop_rate_p) * 50), 2),
            },
        }

    # Team comp stats
    team_comp_summary: dict[str, list[float]] = {}
    for e in completed:
        team_comp_summary.setdefault(e.team_composition, []).append(e.reward)
    team_comp = {
        comp: {"count": len(rs), "avg_reward": round(sum(rs) / len(rs), 4)} for comp, rs in team_comp_summary.items()
    }

    # Reward distribution
    reward_stats: dict[str, float] = {}
    if rewards:
        reward_stats = {
            "mean": round(statistics.mean(rewards), 4),
            "median": round(statistics.median(rewards), 4),
            "min": round(min(rewards), 4),
            "max": round(max(rewards), 4),
            "p25": round(sorted(rewards)[len(rewards) // 4], 4),
            "p75": round(sorted(rewards)[3 * len(rewards) // 4], 4),
        }
        if len(rewards) >= 2:
            reward_stats["std"] = round(statistics.stdev(rewards), 4)

    d = derived
    return {
        "policy": policy_info.model_dump(),
        "episode_count": len(episodes),
        "completed_count": len(completed),
        "season": season,
        "kpis": {
            "avg_reward": round(d.avg_reward, 4),
            "move_efficiency": round(d.move_efficiency, 4),
            "action_success_rate": round(d.action_success_rate, 4),
            "vibe_change_rate": round(d.vibe_change_rate, 4),
            "resource_retention": round(d.resource_retention, 4),
            "freeze_vulnerability": round(d.freeze_vulnerability, 4),
            "junction_control_rate": round(d.junction_control_rate, 4),
            "alignment_stability": round(d.alignment_stability, 4),
            "net_alignment_rate": round(d.net_alignment_rate, 4),
            "noop_rate": round(d.noop_rate, 4),
            "resource_efficiency_per_step": round(d.resource_efficiency_per_step, 4),
            "hearts_to_junction_rate": round(d.hearts_to_junction_rate, 4),
            "reward_consistency": round(d.reward_consistency, 4),
            "reward_nonzero_pct": round(d.reward_nonzero_pct, 4),
        },
        "strategy_profile": {
            "aggressive": round(d.profile_aggressive, 2),
            "defensive": round(d.profile_defensive, 2),
            "resource_hoarder": round(d.profile_resource_hoarder, 2),
            "junction_hunter": round(d.profile_junction_hunter, 2),
            "mobile_scout": round(d.profile_mobile_scout, 2),
        },
        "diagnostics": d.diagnostics,
        "team_comp": team_comp,
        "opponents": opponent_summary,
        "reward_distribution": reward_stats,
    }


# Embed the analysis guide as a module constant to avoid file I/O at request time.
_ANALYSIS_GUIDE_PATH = (
    __import__("pathlib").Path(__file__).parent.parent.parent.parent.parent
    / "skills"
    / "cg.policy-dashboard"
    / "analysis-guide.md"
)


def _load_analysis_guide() -> str:
    """Load the analysis guide, falling back to a minimal version if not found."""
    if _ANALYSIS_GUIDE_PATH.exists():
        return _ANALYSIS_GUIDE_PATH.read_text()
    return "Analyze the policy metrics and provide strategic advice for CoGames tournament play."


def build_analysis_prompt(summary: dict[str, Any]) -> str:
    """Build the Claude analysis prompt with embedded guide and summary data."""
    guide_text = _load_analysis_guide()
    summary_json = json.dumps(summary, indent=2)

    sections = [
        "You are a CoGames tournament policy analyst.",
        "Analyze the following policy performance data and provide strategic advice.",
        "",
        "## Reference Guide",
        "",
        guide_text,
        "",
        "## Policy Performance Summary",
        "",
        f"```json\n{summary_json}\n```",
        "",
        "## Instructions",
        "",
        "Produce a markdown analysis with exactly these"
        " 4 sections. Do NOT repeat diagnostic messages"
        " verbatim — synthesize them into root causes"
        " and actionable advice.",
        "",
        "### Root Cause Analysis",
        "Connect multiple diagnostics and metrics to"
        " identify underlying causes. Look for patterns"
        " across KPIs, matchups, and team compositions"
        " that point to the same root issue.",
        "",
        "### Top 3 Training Priorities",
        "Rank by expected ROI. For each priority, specify"
        " concrete changes: reward shaping adjustments,"
        " curriculum modifications, hyperparameter changes,"
        " or architectural improvements.",
        "",
        "### Opponent Adaptation",
        "For low-performing matchups, analyze the"
        " opponent's strategy profile and suggest"
        " counter-strategies. If no matchup data exists,"
        " skip this section.",
        "",
        "### Policy Narrative",
        "A plain-language description (2-3 sentences) of"
        ' what this policy "feels like" — its personality,'
        " strengths, and blind spots. Write this for"
        " someone who hasn't seen the data.",
    ]
    return "\n".join(sections)
