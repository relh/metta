from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from metta.app_backend.tournament.referees.envs import GameEnvGenerator
from metta.app_backend.tournament.referees.teams.constants import MAX_FAILED_ATTEMPTS


@dataclass
class ElimResult:
    survivors: set[UUID]
    eliminated: dict[UUID, str] = field(default_factory=dict)

    def intersect(self, other: ElimResult) -> ElimResult:
        new_survivors = self.survivors & other.survivors
        eliminated = dict(self.eliminated)
        eliminated.update(other.eliminated)
        eliminated = {pv_id: reason for pv_id, reason in eliminated.items() if pv_id not in new_survivors}
        return ElimResult(survivors=new_survivors, eliminated=eliminated)


class ThresholdElim(BaseModel):
    min_score: float = Field(description="Policies scoring below this are eliminated")

    def apply(self, policy_scores: dict[UUID, float]) -> ElimResult:
        survivors: set[UUID] = set()
        eliminated: dict[UUID, str] = {}
        for pv_id, score in policy_scores.items():
            if score >= self.min_score:
                survivors.add(pv_id)
            else:
                eliminated[pv_id] = f"score {score} < threshold {self.min_score}"
        return ElimResult(survivors=survivors, eliminated=eliminated)


class FractionElim(BaseModel):
    fraction: float = Field(description="Fraction of lowest-scoring policies to eliminate (0.0-1.0)")

    def apply(self, policy_scores: dict[UUID, float]) -> ElimResult:
        ranked = sorted(policy_scores.items(), key=lambda row: row[1], reverse=True)
        cutoff = max(1, int(len(ranked) * (1 - self.fraction)))
        survivors = {pv_id for pv_id, _ in ranked[:cutoff]}
        eliminated = {
            pv_id: f"ranked {i + 1}/{len(ranked)}, bottom {int(self.fraction * 100)}% culled"
            for i, (pv_id, _) in enumerate(ranked)
            if pv_id not in survivors
        }
        return ElimResult(survivors=survivors, eliminated=eliminated)


class TopKElim(BaseModel):
    max_policies: int = Field(ge=1, description="Keep at most this many top-scoring policies")

    def apply(self, policy_scores: dict[UUID, float]) -> ElimResult:
        ranked = sorted(policy_scores.items(), key=lambda row: row[1], reverse=True)
        survivors = {pv_id for pv_id, _ in ranked[: self.max_policies]}
        eliminated = {
            pv_id: f"ranked {i + 1}/{len(ranked)}, top {self.max_policies} kept"
            for i, (pv_id, _) in enumerate(ranked)
            if pv_id not in survivors
        }
        return ElimResult(survivors=survivors, eliminated=eliminated)


SingleElimination = ThresholdElim | FractionElim | TopKElim


class AllOfElim(BaseModel):
    rules: list[SingleElimination] = Field(description="All rules must pass; survivors are the intersection")

    def apply(self, policy_scores: dict[UUID, float]) -> ElimResult:
        result = ElimResult(survivors=set(policy_scores.keys()))
        for rule in self.rules:
            result = result.intersect(rule.apply(policy_scores))
        return result


Elimination = SingleElimination | AllOfElim
TeamTournamentStageKind = Literal["policy_eval", "sample_teams", "team_eval", "score_policies"]


def _elim_description(elim: Elimination) -> str:
    match elim:
        case ThresholdElim(min_score=ms):
            return f"eliminate below {ms} score"
        case FractionElim(fraction=f):
            return f"eliminate bottom {int(f * 100)}%"
        case TopKElim(max_policies=k):
            return f"keep top {k}"
        case AllOfElim(rules=rules):
            return ", ".join(_elim_description(r) for r in rules)


class PolicyEvalStage(BaseModel):
    kind: Literal["policy_eval"] = "policy_eval"
    display_name: str | None = Field(default=None, description="Optional UI title for this stage")
    policies_per_team: int = Field(description="Number of policies composing each team in this eval stage")
    matches_per_combo: int = Field(default=10, description="Matches to play per unique team combination")
    elim: Elimination | None = Field(default=None, description="Elimination rule applied after this stage completes")
    min_policies: int | None = Field(default=None, description="Minimum policies required before this stage starts")

    @property
    def description(self) -> str:
        desc = f"{self.policies_per_team}-policy teams, {self.matches_per_combo} matches per combo"
        if self.elim is not None:
            desc += f", {_elim_description(self.elim)}"
        return desc


class SampleStage(BaseModel):
    kind: Literal["sample_teams"] = "sample_teams"
    display_name: str | None = Field(default=None, description="Optional UI title for this stage")
    team_size: int = Field(description="Number of policies per sampled team")
    num_teams: int = Field(description="Total number of teams to sample")
    min_per_policy: int | None = Field(default=None, description="Minimum teams each policy must appear in")

    @property
    def description(self) -> str:
        return f"Sample {self.num_teams} random {self.team_size}-policy teams weighted by score (with replacement)"


class TeamEvalStage(BaseModel):
    kind: Literal["team_eval"] = "team_eval"
    display_name: str | None = Field(default=None, description="Optional UI title for this stage")
    matches_per_team: int = Field(description="Matches each team plays in this round")
    cull_fraction: float = Field(description="Fraction of lowest-scoring teams culled after this round (0.0-1.0)")

    @property
    def description(self) -> str:
        if self.cull_fraction == 0:
            return f"Final round: {self.matches_per_team} matches per team"
        return f"{self.matches_per_team} matches per team, cull bottom {int(self.cull_fraction * 100)}%"


class ScoreStage(BaseModel):
    kind: Literal["score_policies"] = "score_policies"
    display_name: str | None = Field(default=None, description="Optional UI title for this stage")
    top_k: int = Field(description="Number of best team placements used per policy")

    @property
    def description(self) -> str:
        return (
            f"Score policies by sum of top {self.top_k} team placements; if a policy appears in fewer than "
            f"{self.top_k} ranked teams, each missing placement counts as (total ranked teams + 1). Lower is better."
        )


TeamTournamentStage = Annotated[
    PolicyEvalStage | SampleStage | TeamEvalStage | ScoreStage,
    Field(discriminator="kind"),
]


class TeamTournamentConfig(BaseModel):
    game: GameEnvGenerator = Field(default_factory=GameEnvGenerator, description="Game environment configuration")
    stages: list[TeamTournamentStage] = Field(description="Ordered tournament stages")
    fixed_map_seed: int | None = Field(default=None, description="When set, all matches use this map seed")
    max_failed_attempts: int = Field(
        default=MAX_FAILED_ATTEMPTS,
        ge=1,
        description=(
            "Maximum failed attempts per combo/team before scheduling is stopped and entries are treated as exhausted"
        ),
    )

    @model_validator(mode="after")
    def _validate_stage_compatibility(self) -> TeamTournamentConfig:
        policy_eval_seen = 0
        sample_stage: SampleStage | None = None
        team_eval_seen = 0
        score_stage: ScoreStage | None = None

        for stage in self.stages:
            match stage:
                case PolicyEvalStage():
                    if sample_stage is not None:
                        raise ValueError("Policy eval stages must come before team sampling")
                    policy_eval_seen += 1
                    if self.game.num_agents % stage.policies_per_team != 0:
                        raise ValueError(
                            f"num_agents ({self.game.num_agents}) must be divisible by "
                            f"policies_per_team ({stage.policies_per_team})"
                        )
                case SampleStage():
                    if sample_stage is not None:
                        raise ValueError("Exactly one sample_teams stage is required")
                    sample_stage = stage
                    if self.game.num_agents % stage.team_size != 0:
                        raise ValueError(
                            f"num_agents ({self.game.num_agents}) must be divisible by team_size ({stage.team_size})"
                        )
                case TeamEvalStage():
                    if sample_stage is None:
                        raise ValueError("team_eval stages require a preceding sample_teams stage")
                    if score_stage is not None:
                        raise ValueError("team_eval stages must come before score_policies")
                    team_eval_seen += 1
                case ScoreStage():
                    if sample_stage is None:
                        raise ValueError("score_policies requires a preceding sample_teams stage")
                    if score_stage is not None:
                        raise ValueError("Exactly one score_policies stage is required")
                    score_stage = stage

        if policy_eval_seen == 0:
            raise ValueError("At least one policy_eval stage is required")
        if sample_stage is None:
            raise ValueError("A sample_teams stage is required")
        if team_eval_seen == 0:
            raise ValueError("At least one team_eval stage is required")
        if score_stage is None:
            raise ValueError("A score_policies stage is required")
        if self.stages[-1].kind != "score_policies":
            raise ValueError("score_policies must be the final stage")

        return self

    @property
    def policy_eval_stages(self) -> list[PolicyEvalStage]:
        return [stage for stage in self.stages if isinstance(stage, PolicyEvalStage)]

    @property
    def sample_stage(self) -> SampleStage:
        for stage in self.stages:
            if isinstance(stage, SampleStage):
                return stage
        raise AssertionError("sample_teams stage is required")

    @property
    def team_eval_stages(self) -> list[TeamEvalStage]:
        return [stage for stage in self.stages if isinstance(stage, TeamEvalStage)]

    @property
    def score_stage(self) -> ScoreStage:
        for stage in self.stages:
            if isinstance(stage, ScoreStage):
                return stage
        raise AssertionError("score_policies stage is required")

    @property
    def min_teams_per_policy(self) -> int:
        mp = self.sample_stage.min_per_policy
        return mp if mp is not None else self.score_stage.top_k
