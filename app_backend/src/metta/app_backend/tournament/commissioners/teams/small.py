from metta.app_backend.tournament.commissioners.teams.beta import BetaTeamsCommissioner
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


class BetaTeamsSmallCommissioner(BetaTeamsCommissioner):
    season_name = "beta-teams-small"
    display_name = "Beta Teams Tournament"
    initial_config = TeamTournamentConfig(
        game=GameEnvGenerator(num_agents=8),
        stages=[
            PolicyEvalStage(
                policies_per_team=1,
                matches_per_combo=2,
                min_policies=8,
                elim=ThresholdElim(min_score=0.01),
            ),
            PolicyEvalStage(
                policies_per_team=2,
                matches_per_combo=2,
                min_policies=8,
                elim=FractionElim(fraction=0.05),
            ),
            PolicyEvalStage(policies_per_team=4, matches_per_combo=2),
            SampleStage(team_size=8, num_teams=64, min_per_policy=4),
            TeamEvalStage(matches_per_team=10, cull_fraction=0.5),
            TeamEvalStage(matches_per_team=10, cull_fraction=0.5),
            TeamEvalStage(matches_per_team=10, cull_fraction=0.0),
            ScoreStage(top_k=4),
        ],
    )
