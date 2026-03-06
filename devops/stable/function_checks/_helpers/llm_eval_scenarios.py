from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LLMEvalScenario:
    name: str
    task: str
    requires_auth: bool = False
    timeout_s: int = 300
    max_agent_turns: int = 20


SCENARIOS: dict[str, LLMEvalScenario] = {}


def _register(scenario: LLMEvalScenario) -> LLMEvalScenario:
    SCENARIOS[scenario.name] = scenario
    return scenario


_register(
    LLMEvalScenario(
        name="spectator_leaderboard",
        task=(
            "I want to check on the current tournament standings. Who's winning? "
            "I don't have an account and I'm not logged in. "
            "Show me the current leaderboard rankings with scores."
        ),
    )
)

_register(
    LLMEvalScenario(
        name="tournament_progress",
        task=(
            "I'm watching a tournament and it hasn't seemed to update in a while. "
            "Can you check what's going on with the current season? Is it stuck? "
            "What stage is it in? How many matches have been played?"
        ),
    )
)

_register(
    LLMEvalScenario(
        name="important_tournaments",
        task=(
            "What tournaments are running right now? Which ones are the important ones? "
            "I want to know which seasons are active, which is the default, "
            "and what type of tournament each one is."
        ),
    )
)

_register(
    LLMEvalScenario(
        name="debug_submission_error",
        task=(
            "I submitted a policy recently and it seems to have errored during evaluation. "
            "How do I figure out what went wrong? Show me how to check the status of my "
            "submissions, find the one that failed, and pull up any logs or error details. "
            "Walk me through the debugging workflow."
        ),
        requires_auth=True,
    )
)

_register(
    LLMEvalScenario(
        name="debug_submission_performance",
        task=(
            "My policy got submitted and ran in the tournament but it's doing terribly. "
            "I want to understand why. How do I look at my match results, see what happened "
            "in specific episodes, and figure out where my policy is failing? "
            "Show me the diagnostic tools available."
        ),
        requires_auth=True,
    )
)

_register(
    LLMEvalScenario(
        name="tournament_game_rules",
        task=(
            "I see there are different tournaments and missions. "
            "What are the actual differences in game rules between them? "
            "I want to understand the different mission types, what the objectives are, "
            "and how the game mechanics differ across tournament configurations."
        ),
    )
)
