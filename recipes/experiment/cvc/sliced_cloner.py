"""Cogsguard sliced-cloner entry points (legacy CVC wrapper)."""

from recipes.experiment.cvc.cloner import evaluate, play, replay, train

__all__ = ["train", "evaluate", "play", "replay"]
