from metta.app_backend.tournament.commissioners.teams.beta import BetaTeamsCommissioner
from metta.app_backend.tournament.commissioners.teams.config import (
    AllOfElim,
    GameEnvGenerator,
    PolicyEvalStage,
    SampleStage,
    ScoreStage,
    TeamEvalStage,
    TeamTournamentConfig,
    ThresholdElim,
    TopKElim,
)


class BetaTeamsSmallCommissioner(BetaTeamsCommissioner):
    season_name = "beta-teams-small"
    display_name = "Beta Teams Tournament"
    initial_config = TeamTournamentConfig(
        game=GameEnvGenerator(num_agents=8),
        stages=[
            PolicyEvalStage(
                display_name="Play-ins: one-player",
                policies_per_team=1,
                matches_per_combo=5,
                min_policies=8,
                elim=TopKElim(max_policies=32),
            ),
            PolicyEvalStage(
                display_name="Play-ins: two-player",
                policies_per_team=2,
                matches_per_combo=2,
                min_policies=8,
                elim=TopKElim(max_policies=16),
            ),
            PolicyEvalStage(
                display_name="Play-ins: four-player",
                policies_per_team=4,
                matches_per_combo=2,
                elim=TopKElim(max_policies=16),
            ),
            SampleStage(display_name="Sampling: eight-player", team_size=8, num_teams=64, min_per_policy=4),
            TeamEvalStage(display_name="Playoffs: eight-player", matches_per_team=10, cull_fraction=0.5),
            TeamEvalStage(display_name="Playoffs: eight-player", matches_per_team=10, cull_fraction=0.5),
            TeamEvalStage(display_name="Playoffs: eight-player", matches_per_team=10, cull_fraction=0.0),
            ScoreStage(display_name="Final scoring", top_k=4),
        ],
    )


class BetaTeamsTinyFixedCommissioner(BetaTeamsCommissioner):
    season_name = "beta-teams-tiny-fixed"
    display_name = "Beta Teams Tournament (Tiny, Fixed Map Seed)"
    initial_config = TeamTournamentConfig(
        game=GameEnvGenerator(num_agents=8),
        fixed_map_seed=42,
        stages=[
            PolicyEvalStage(
                display_name="Play-ins: one-player",
                policies_per_team=1,
                matches_per_combo=3,
                min_policies=4,
                elim=AllOfElim(rules=[ThresholdElim(min_score=1), TopKElim(max_policies=16)]),
            ),
            PolicyEvalStage(
                display_name="Play-ins: two-player",
                policies_per_team=2,
                matches_per_combo=2,
                min_policies=4,
                elim=TopKElim(max_policies=12),
            ),
            PolicyEvalStage(
                display_name="Play-ins: four-player",
                policies_per_team=4,
                matches_per_combo=2,
                elim=TopKElim(max_policies=10),
            ),
            SampleStage(display_name="Sampling: eight-player", team_size=8, num_teams=24, min_per_policy=1),
            TeamEvalStage(display_name="Playoffs: eight-player", matches_per_team=5, cull_fraction=0.5),
            TeamEvalStage(display_name="Playoffs: eight-player", matches_per_team=5, cull_fraction=0.0),
            ScoreStage(display_name="Final scoring", top_k=4),
        ],
    )
