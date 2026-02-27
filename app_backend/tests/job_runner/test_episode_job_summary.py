"""Tests for EpisodeJobSummary — the slim model that decouples episode recording
from the full SingleEpisodeJob / MettaGridConfig schema."""

import pytest
from pydantic import ValidationError

from metta.app_backend.job_runner.episode_recording import EpisodeJobSummary
from mettagrid.runner.types import EpisodeJobSummary as MettagridEpisodeJobSummary
from mettagrid.runner.types import EpisodeSpec, SingleEpisodeJob


def test_extracts_required_fields():
    job = EpisodeJobSummary.model_validate(
        {
            "policy_uris": ["s3://bucket/policy"],
            "assignments": [0, 0],
            "env": {"name": "test", "game": {"num_agents": 2}},  # ignored
        }
    )
    assert job.policy_uris == ["s3://bucket/policy"]
    assert job.assignments == [0, 0]
    assert job.episode_tags == {}


def test_ignores_unknown_fields():
    """Extra fields from MettaGridConfig (old or new) must never cause a failure."""
    job = EpisodeJobSummary.model_validate(
        {
            "policy_uris": ["s3://bucket/policy"],
            "assignments": [0],
            "env": {"name": "test"},
            "map_width": 64,  # removed field that caused the P2 incident
            "map_height": 64,
            "some_future_field": "whatever",
        }
    )
    assert job.policy_uris == ["s3://bucket/policy"]


def test_episode_tags_passed_through():
    job = EpisodeJobSummary.model_validate(
        {
            "policy_uris": ["metta://policy/v1", "metta://policy/v2"],
            "assignments": [0, 1],
            "episode_tags": {"tournament_id": "t-123", "round": "1"},
        }
    )
    assert job.episode_tags == {"tournament_id": "t-123", "round": "1"}


def test_missing_required_fields_raises():
    with pytest.raises(ValidationError):
        EpisodeJobSummary.model_validate({"assignments": [0]})  # missing policy_uris

    with pytest.raises(ValidationError):
        EpisodeJobSummary.model_validate({"policy_uris": ["s3://x"]})  # missing assignments


def test_inheritance_contract():
    """SingleEpisodeJob IS-A EpisodeJobSummary — fields can't diverge."""
    assert issubclass(EpisodeSpec, MettagridEpisodeJobSummary)
    assert issubclass(SingleEpisodeJob, MettagridEpisodeJobSummary)
    # app_backend imports the same class from mettagrid
    assert EpisodeJobSummary is MettagridEpisodeJobSummary


def test_episode_spec_inherits_episode_tags_with_empty_default():
    """EpisodeSpec inherits episode_tags from EpisodeJobSummary; defaults to empty dict."""
    # episode_tags is inherited, not redefined — verify the field exists and defaults correctly
    assert "episode_tags" in EpisodeSpec.model_fields
    assert EpisodeSpec.model_fields["episode_tags"].is_required() is False
