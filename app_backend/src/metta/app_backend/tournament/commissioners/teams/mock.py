from metta.app_backend.tournament.commissioners.mock import MockMatchExecutionMixin
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
from metta.app_backend.tournament.referees.teams.policy_stage import MockPolicyStageReferee, PolicyStageReferee
from metta.app_backend.tournament.referees.teams.score_stage import ScoreStageReferee


class MockTeamsCommissioner(MockMatchExecutionMixin, TeamCommissionerBase):
    season_name = "teams-mock"
    summary = "Fast local-only mock team tournament with mock scores and visible stage progress"
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
                policies_per_team=1,
                matches_per_combo=1,
                min_policies=8,
                elim=ThresholdElim(min_score=0.05),
            ),
            PolicyEvalStage(
                policies_per_team=2,
                matches_per_combo=1,
                min_policies=8,
                elim=FractionElim(fraction=0.25),
            ),
            PolicyEvalStage(policies_per_team=4, matches_per_combo=1),
            SampleStage(team_size=8, num_teams=48, min_per_policy=4),
            TeamEvalStage(matches_per_team=2, cull_fraction=0.5),
            TeamEvalStage(matches_per_team=2, cull_fraction=0.5),
            TeamEvalStage(matches_per_team=2, cull_fraction=0.0),
            ScoreStage(top_k=4),
        ],
        max_outstanding_matches=6,
    )

    def _policy_referee(self, stage: PolicyEvalStage) -> PolicyStageReferee:
        return MockPolicyStageReferee(
            stage=stage,
            game=self.config.game,
        )
