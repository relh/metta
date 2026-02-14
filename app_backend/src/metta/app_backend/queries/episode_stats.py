import json
from collections import defaultdict
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from metta.app_backend.models.episodes import Episode
from metta.app_backend.models.job_request import JobPolicyVersion
from metta.app_backend.models.policies import PolicyVersion


class PolicyVersionSummary(BaseModel):
    id: UUID = Field(description="Unique identifier of the policy version")
    name: str | None = Field(description="Human-readable policy name")
    version: int | None = Field(description="Sequential version number within the policy")

    @classmethod
    def from_model(cls, pv: PolicyVersion) -> "PolicyVersionSummary":
        return cls(id=pv.id, name=pv.policy.name, version=pv.version)


class AgentResult(BaseModel):
    agent_id: int = Field(description="Index of the agent within the episode")
    reward: float = Field(description="Total reward earned by this agent")
    metrics: dict[str, float] = Field(
        description="Per-agent game metrics accumulated over the episode. "
        "Keys use dotted names: action stats (action.move.success, action.move.failed, action.noop.success, "
        "action.change_vibe.success, action.failed), resource stats with .amount/.gained/.lost suffixes "
        "(energy, heart, hp, influence), role stats with .amount/.gained/.lost suffixes "
        "(miner, aligner, scout, scrambler), junction.aligned_by_agent, "
        "and status.max_steps_without_motion.",
        json_schema_extra={
            "examples": [
                {
                    "action.move.success": 623.0,
                    "action.move.failed": 51.0,
                    "action.noop.success": 326.0,
                    "energy.amount": 8.0,
                    "energy.gained": 1954.0,
                    "energy.lost": 1946.0,
                    "hp.amount": 67.0,
                    "hp.gained": 1075.0,
                    "hp.lost": 1008.0,
                    "junction.aligned_by_agent": 2.0,
                    "status.max_steps_without_motion": 17.0,
                }
            ]
        },
    )


class PolicyResult(BaseModel):
    position: int = Field(description="Policy position index in the match assignment")
    policy: PolicyVersionSummary = Field(description="Identity of the policy version")
    num_agents: int = Field(description="Number of agents controlled by this policy")
    avg_reward: float = Field(description="Mean reward across all agents for this policy")
    avg_metrics: dict[str, float] = Field(
        description="Mean of each metric across all agents for this policy. "
        "Same keys as AgentResult.metrics — see that field for the full key reference."
    )
    agents: list[AgentResult] = Field(description="Per-agent breakdown of rewards and metrics")


class EpisodeResponse(BaseModel):
    id: UUID = Field(description="Unique episode identifier")
    replay_url: str | None = Field(description="URL to the episode replay recording")
    thumbnail_url: str | None = Field(description="URL to a thumbnail image of the episode")
    tags: dict[str, str] = Field(
        description="Key-value tags attached to this episode. "
        "Common keys: game (game name, e.g. 'cogsguard'), match_type (e.g. 'self_play', 'pairing'), "
        "job_id, scheduler_git_ref."
    )
    game_stats: dict[str, float] = Field(
        description="Game-level aggregate statistics. "
        "Keys include object counts (objects.<type>, e.g. objects.junction, objects.wall, "
        "objects.agent.agent, objects.hub, objects.chest, objects.*_extractor, objects.*_station) "
        "and observation token stats (tokens_written, tokens_dropped, tokens_free_space).",
        json_schema_extra={
            "examples": [
                {
                    "objects.agent.agent": 10.0,
                    "objects.junction": 107.0,
                    "objects.wall": 3304.0,
                    "objects.hub": 1.0,
                    "objects.chest": 2.0,
                    "objects.carbon_extractor": 48.0,
                    "objects.aligner_station": 1.0,
                    "tokens_written": 379639.0,
                    "tokens_dropped": 0.0,
                    "tokens_free_space": 1622361.0,
                }
            ]
        },
    )
    policy_results: list[PolicyResult] = Field(description="Results broken down by policy")
    steps: int | None = Field(description="Number of environment steps in the episode")
    created_at: datetime = Field(description="When the episode was recorded")


def _build_policy_map(policy_versions: list[JobPolicyVersion]) -> dict[int, PolicyVersionSummary]:
    return {
        jpv.position: PolicyVersionSummary.from_model(jpv.policy_version)
        for jpv in policy_versions
        if jpv.policy_version
    }


def compute_episode_stats(
    episode: Episode,
    assignments: list[int],
    policy_versions: list[JobPolicyVersion],
) -> tuple[dict[str, float], list[PolicyResult], int | None]:
    policy_map = _build_policy_map(policy_versions)
    raw_attrs = episode.attributes or {}
    parsed = json.loads(raw_attrs) if isinstance(raw_attrs, str) else raw_attrs
    attributes = parsed if isinstance(parsed, dict) else {}
    stats = attributes.get("stats", {})
    agent_stats_list: list[dict[str, float]] = stats.get("agent", [])
    rewards_list: list[float] = attributes.get("rewards", [])
    game_stats: dict[str, float] = stats.get("game", {})
    steps: int | None = attributes.get("steps") or stats.get("steps")

    policy_agents: dict[int, list[tuple[int, dict[str, float], float]]] = defaultdict(list)
    for agent_id, agent_metrics in enumerate(agent_stats_list):
        policy_idx = assignments[agent_id] if agent_id < len(assignments) else -1
        reward = rewards_list[agent_id] if agent_id < len(rewards_list) else 0.0
        policy_agents[policy_idx].append((agent_id, agent_metrics, reward))

    policy_results: list[PolicyResult] = []
    for position in sorted(policy_agents.keys()):
        agents = policy_agents[position]
        policy_summary = policy_map.get(position, PolicyVersionSummary(id=UUID(int=0), name=None, version=None))

        all_metric_names: set[str] = set()
        for _, metrics, _ in agents:
            all_metric_names.update(metrics.keys())

        avg_metrics: dict[str, float] = {}
        for name in sorted(all_metric_names):
            values = [m[name] for _, m, _ in agents if name in m and m[name] is not None]
            if values:
                avg_metrics[name] = sum(values) / len(values)

        reward_values = [r for _, _, r in agents]
        avg_reward = sum(reward_values) / len(reward_values) if reward_values else 0.0

        agent_results = [
            AgentResult(
                agent_id=aid,
                reward=reward,
                metrics={k: v for k, v in metrics.items() if v is not None},
            )
            for aid, metrics, reward in agents
        ]

        policy_results.append(
            PolicyResult(
                position=position,
                policy=policy_summary,
                num_agents=len(agents),
                avg_reward=avg_reward,
                avg_metrics=avg_metrics,
                agents=agent_results,
            )
        )

    return game_stats, policy_results, steps


def build_episode_response(
    episode: Episode,
    assignments: list[int],
    policy_versions: list[JobPolicyVersion],
) -> EpisodeResponse:
    game_stats, policy_results, steps = compute_episode_stats(episode, assignments, policy_versions)
    return EpisodeResponse(
        id=episode.id,
        replay_url=episode.replay_url,
        thumbnail_url=episode.thumbnail_url,
        tags={t.key: t.value for t in episode.tags},
        game_stats=game_stats,
        policy_results=policy_results,
        steps=steps,
        created_at=episode.created_at,
    )
