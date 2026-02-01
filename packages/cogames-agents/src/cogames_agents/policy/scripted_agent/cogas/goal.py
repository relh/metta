"""Goal base class and evaluation logic for Cogas policy."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from mettagrid.simulator import Action

if TYPE_CHECKING:
    from .context import CogasContext


class Goal:
    """Base class for all goals in the goal tree.

    Subclasses implement:
    - is_satisfied(ctx) -> bool: whether this goal is already met
    - preconditions() -> list[Goal]: sub-goals that must be satisfied first
    - execute(ctx) -> Action | None: produce an action, or None to skip/defer
    """

    name: str = "Goal"

    def is_satisfied(self, ctx: CogasContext) -> bool:
        """Check if this goal is already satisfied."""
        return False

    def preconditions(self) -> list[Goal]:
        """Return sub-goals that must be satisfied before this goal can execute."""
        return []

    def execute(self, ctx: CogasContext) -> Optional[Action]:
        """Produce an action to work toward this goal, or None to skip."""
        return Action(name="noop")


def evaluate_goals(goals: list[Goal], ctx: CogasContext) -> Action:
    """Evaluate a priority-ordered goal list and return an action.

    Walks the list top-down. The first unsatisfied goal becomes active.
    Recursively checks preconditions to find the deepest unsatisfied leaf.
    That leaf's execute() produces the action.

    If execute() returns None, the goal is skipped and evaluation continues
    with the next goal (allows goals to voluntarily defer).
    """
    for goal in goals:
        if goal.is_satisfied(ctx):
            if ctx.trace:
                ctx.trace.skip(goal.name, _satisfaction_detail(goal, ctx))
            continue

        # Found unsatisfied goal — recurse into preconditions
        leaf = _deepest_unsatisfied(goal, ctx)
        action = leaf.execute(ctx)

        # None means "skip me for now" — continue to next goal
        if action is None:
            if ctx.trace:
                ctx.trace.skip(leaf.name, "deferred")
            continue

        if ctx.trace:
            ctx.trace.active_goal_chain = _build_chain(goal, leaf)
            ctx.trace.action_name = action.name

        return action

    # All goals satisfied - explore as fallback instead of nooping
    if ctx.trace:
        ctx.trace.active_goal_chain = "AllGoalsSatisfied"
    directions = ["north", "east", "south", "west"]
    return ctx.navigator.explore(
        ctx.state.position,
        ctx.map,
        direction_bias=directions[ctx.agent_id % 4],
    )


def _deepest_unsatisfied(goal: Goal, ctx: CogasContext) -> Goal:
    """Find the deepest unsatisfied precondition in the goal tree."""
    for pre in goal.preconditions():
        if not pre.is_satisfied(ctx):
            if ctx.trace:
                ctx.trace.activate(pre.name)
            return _deepest_unsatisfied(pre, ctx)
    return goal


def _build_chain(root: Goal, leaf: Goal) -> str:
    """Build a display chain like 'MineCarbon>BeNearExtractor'."""
    if root is leaf:
        return root.name
    # Walk preconditions to find the path
    chain = [root.name]
    _find_path(root, leaf, chain)
    return ">".join(chain)


def _find_path(current: Goal, target: Goal, chain: list[str]) -> bool:
    """DFS to find path from current to target goal."""
    for pre in current.preconditions():
        if pre is target:
            chain.append(pre.name)
            return True
        chain.append(pre.name)
        if _find_path(pre, target, chain):
            return True
        chain.pop()
    return False


def _satisfaction_detail(goal: Goal, ctx: CogasContext) -> str:
    """Generate a short detail string for why a goal is satisfied."""
    return "ok"
