from metta.app_backend.tournament.commissioners.teams.base import TeamCommissionerBase
from metta.app_backend.tournament.commissioners.teams.config import (
    FractionElim,
    GameEnvGenerator,
    PolicyEvalStage,
    SampleStage,
    ScoreStage,
    TeamEvalStage,
    TeamTournamentConfig,
    ThresholdElim,
)
from metta.app_backend.tournament.commissioners.teams.stage_planning import _policy_pool, _score_pool, _team_pool
from metta.app_backend.tournament.referees.teams.policy_stage import PolicyStageReferee
from metta.app_backend.tournament.referees.teams.score_stage import ScoreStageReferee


class BetaTeamsCommissioner(TeamCommissionerBase):
    season_name = "beta-teams-large"
    summary = "Progressive-widening team tournament: 1->2->4->8 policy teams"
    entry_pool = _policy_pool(1)
    leaderboard_pool = _score_pool()
    referees = {
        entry_pool: PolicyStageReferee(
            stage=PolicyEvalStage(policies_per_team=1, matches_per_combo=10),
            game=GameEnvGenerator(num_agents=8),
        ),
        leaderboard_pool: ScoreStageReferee(source_team_pool_name=_team_pool(1), top_k=1),
    }
    initial_config = TeamTournamentConfig(
        game=GameEnvGenerator(num_agents=8),
        stages=[
            PolicyEvalStage(
                policies_per_team=1, matches_per_combo=2, min_policies=8, elim=ThresholdElim(min_score=0.01)
            ),
            PolicyEvalStage(policies_per_team=2, matches_per_combo=2, min_policies=8, elim=FractionElim(fraction=0.25)),
            PolicyEvalStage(policies_per_team=4, matches_per_combo=2),
            SampleStage(team_size=8, num_teams=1000),
            TeamEvalStage(matches_per_team=10, cull_fraction=0.5),
            TeamEvalStage(matches_per_team=10, cull_fraction=0.5),
            TeamEvalStage(matches_per_team=10, cull_fraction=0.0),
            ScoreStage(top_k=10),
        ],
    )
