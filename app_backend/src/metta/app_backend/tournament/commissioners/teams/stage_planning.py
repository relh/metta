from __future__ import annotations

from dataclasses import dataclass

# pyright: reportAttributeAccessIssue=false
from metta.app_backend.tournament.commissioners.base import PoolDescription, SeasonDescription
from metta.app_backend.tournament.commissioners.teams.config import (
    PolicyEvalStage,
    SampleStage,
    ScoreStage,
    TeamEvalStage,
)
from metta.app_backend.tournament.referees.base import RefereeBase
from metta.app_backend.tournament.referees.teams.policy_stage import PolicyStageReferee
from metta.app_backend.tournament.referees.teams.score_stage import ScoreStageReferee
from metta.app_backend.tournament.referees.teams.team_stage import TeamStageReferee


def _policy_pool(n: int) -> str:
    return f"stage-{n}"


def _sample_pool(n: int) -> str:
    return f"sample-{n}"


def _team_pool(n: int) -> str:
    return f"team-round-{n}"


def _score_pool(n: int = 1) -> str:
    return f"policy-scores-{n}"


_NUMBER_WORDS: dict[int, str] = {
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
}


def _player_size_label(player_count: int) -> str:
    word = _NUMBER_WORDS.get(player_count, str(player_count))
    return f"{word}-player"


@dataclass(frozen=True)
class StageBinding:
    index: int
    stage: PolicyEvalStage | SampleStage | TeamEvalStage | ScoreStage
    display_name: str
    input_pool: str
    output_pool: str
    score_source_pool: str | None = None


class TeamStagePlanningMixin:
    def _stage_display_name(self, stage: PolicyEvalStage | SampleStage | TeamEvalStage | ScoreStage) -> str:
        if stage.display_name:
            return stage.display_name

        match stage:
            case PolicyEvalStage():
                return f"Play-ins: {_player_size_label(stage.policies_per_team)}"
            case SampleStage():
                return f"Sampling: {_player_size_label(stage.team_size)}"
            case TeamEvalStage():
                return f"Playoffs: {_player_size_label(self.config.sample_stage.team_size)}"
            case ScoreStage():
                return "Final scoring"

    def _stage_bindings(self) -> list[StageBinding]:
        bindings: list[StageBinding] = []
        policy_pool_num = 1
        sample_pool_num = 1
        team_pool_num = 1
        score_pool_num = 1
        last_policy_eval_pool: str | None = None
        last_team_eval_pool: str | None = None

        for index, stage in enumerate(self.config.stages):
            next_stage = self.config.stages[index + 1] if index + 1 < len(self.config.stages) else None
            score_source_pool: str | None = None
            match stage:
                case PolicyEvalStage():
                    input_pool = _policy_pool(policy_pool_num)
                    if isinstance(next_stage, SampleStage):
                        output_pool = _sample_pool(sample_pool_num)
                    else:
                        output_pool = _policy_pool(policy_pool_num + 1)
                    last_policy_eval_pool = input_pool
                    policy_pool_num += 1
                case SampleStage():
                    input_pool = _sample_pool(sample_pool_num)
                    output_pool = _team_pool(team_pool_num)
                    sample_pool_num += 1
                    assert last_policy_eval_pool is not None
                    score_source_pool = last_policy_eval_pool
                case TeamEvalStage():
                    input_pool = _team_pool(team_pool_num)
                    output_pool = _team_pool(team_pool_num + 1)
                    last_team_eval_pool = input_pool
                    team_pool_num += 1
                case ScoreStage():
                    input_pool = _team_pool(team_pool_num)
                    output_pool = _score_pool(score_pool_num)
                    score_pool_num += 1
                    assert last_team_eval_pool is not None
                    score_source_pool = last_team_eval_pool

            bindings.append(
                StageBinding(
                    index=index,
                    stage=stage,
                    display_name=self._stage_display_name(stage),
                    input_pool=input_pool,
                    output_pool=output_pool,
                    score_source_pool=score_source_pool,
                )
            )

        return bindings

    def _policy_referee(self, stage: PolicyEvalStage) -> PolicyStageReferee:
        return PolicyStageReferee(
            stage=stage,
            game=self.config.game,
            max_failed_attempts=self.config.max_failed_attempts,
            fixed_map_seed=self.config.fixed_map_seed,
        )

    def get_referees(self, season_version: int) -> dict[str, RefereeBase]:  # type: ignore[unused-arg]
        refs: dict[str, RefereeBase] = {}
        for binding in self._stage_bindings():
            match binding.stage:
                case PolicyEvalStage() as stage:
                    refs[binding.input_pool] = self._policy_referee(stage)
                case TeamEvalStage() as stage:
                    refs[binding.input_pool] = TeamStageReferee(
                        matches_per_team=stage.matches_per_team,
                        teams=[],
                        game=self.config.game,
                        max_failed_attempts=self.config.max_failed_attempts,
                        fixed_map_seed=self.config.fixed_map_seed,
                    )
                case ScoreStage() as stage:
                    refs[binding.output_pool] = ScoreStageReferee(
                        source_team_pool_name=binding.score_source_pool or binding.input_pool,
                        top_k=stage.top_k,
                    )

        return refs

    def description_for_version(self, season_version: int = 1) -> SeasonDescription:  # type: ignore[unused-arg]
        pools: list[PoolDescription] = []
        seen: set[str] = set()

        for binding in self._stage_bindings():
            if binding.input_pool not in seen:
                pools.append(PoolDescription(name=binding.input_pool, description=binding.stage.description))
                seen.add(binding.input_pool)
            if binding.stage.kind == "score_policies" and binding.output_pool not in seen:
                pools.append(PoolDescription(name=binding.output_pool, description=binding.stage.description))
                seen.add(binding.output_pool)

        return SeasonDescription(summary=self.summary, pools=pools)
