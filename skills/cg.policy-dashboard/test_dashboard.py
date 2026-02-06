#!/usr/bin/env python3
"""Test suite for the policy dashboard.

Run before committing changes to validate dashboard functionality.
Uses local test fixtures in test_fixtures/ directory.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# Add skill directory to path for imports
SKILL_DIR = Path(__file__).parent
sys.path.insert(0, str(SKILL_DIR))

from generate import (  # noqa: E402
    DashboardData,
    EpisodeData,
    PolicyVersion,
    aggregate_agent_metrics,
    data_to_dict,
    generate_dashboard,
    load_local_results,
    result_to_episode_data,
)


def test_result_to_episode_data_basic():
    """Test basic conversion of result dict to EpisodeData."""
    result = {
        "rewards": [10.0, 12.0, 8.0, 15.0],
        "steps": 5000,
        "stats": {
            "game": {},
            "agent": [
                {"action.move.success": 100.0, "energy.amount": 50.0},
                {"action.move.success": 120.0, "energy.amount": 60.0},
                {"action.move.success": 80.0, "energy.amount": 40.0},
                {"action.move.success": 110.0, "energy.amount": 55.0},
            ],
        },
    }
    assignments = [0, 0, 0, 0]  # All agents belong to policy 0

    episode = result_to_episode_data(
        result_dict=result,
        episode_id="test-001",
        assignments=assignments,
        policy_index=0,
    )

    assert episode.episode_id == "test-001"
    assert episode.steps == 5000
    assert episode.team_composition == "4v0"
    # Reward should be average of all agents (all belong to policy 0)
    assert abs(episode.reward - 11.25) < 0.01  # (10+12+8+15)/4
    # Metrics should be aggregated across all agents
    assert episode.metrics["action.move.success"] == 410.0  # 100+120+80+110
    assert episode.metrics["energy.amount"] == 205.0  # 50+60+40+55


def test_result_to_episode_data_with_opponent():
    """Test conversion with opponent (split assignments)."""
    result = {
        "rewards": [20.0, 25.0, 5.0, 3.0],
        "steps": 8000,
        "stats": {
            "game": {},
            "agent": [
                {"action.move.success": 200.0},
                {"action.move.success": 250.0},
                {"action.move.success": 50.0},
                {"action.move.success": 30.0},
            ],
        },
    }
    # First 2 agents are policy 0, last 2 are policy 1
    assignments = [0, 0, 1, 1]

    episode = result_to_episode_data(
        result_dict=result,
        episode_id="test-002",
        assignments=assignments,
        policy_index=0,
        opponent_name="opponent-policy",
        opponent_version=5,
    )

    assert episode.team_composition == "2v2"
    assert episode.opponent_name == "opponent-policy"
    assert episode.opponent_version == 5
    # Reward should be average of policy 0's agents only
    assert abs(episode.reward - 22.5) < 0.01  # (20+25)/2
    # Metrics should only include policy 0's agents
    assert episode.metrics["action.move.success"] == 450.0  # 200+250


def test_result_to_episode_data_missing_steps():
    """Test handling of missing steps field."""
    result = {
        "rewards": [10.0],
        "stats": {"game": {}, "agent": [{"metric": 1.0}]},
    }

    episode = result_to_episode_data(
        result_dict=result,
        episode_id="test-003",
        assignments=[0],
    )

    assert episode.steps == 0  # Default when missing


def test_aggregate_agent_metrics():
    """Test metric aggregation across agents."""
    agent_stats = [
        {"a": 10.0, "b": 20.0, "c": None},
        {"a": 15.0, "b": 25.0},
        {"a": 5.0, "b": 10.0},
    ]
    assignments = [0, 0, 1]  # First two are ours, third is opponent

    metrics = aggregate_agent_metrics(agent_stats, 3, policy_index=0, assignments=assignments)

    assert metrics["a"] == 25.0  # 10+15
    assert metrics["b"] == 45.0  # 20+25
    assert "c" not in metrics  # None values excluded


def test_load_local_results():
    """Test loading results from test fixtures directory."""
    fixtures_dir = SKILL_DIR / "test_fixtures"

    data = load_local_results(fixtures_dir, "test-policy", limit=100)

    assert data.policy.name == "test-policy"
    assert data.policy.id == "local"
    assert data.season == "local"
    assert len(data.episodes) >= 3  # We have at least 3 valid fixtures

    # Verify episodes have expected data
    for ep in data.episodes:
        assert ep.steps > 0
        assert ep.reward > 0
        assert len(ep.metrics) > 0
        assert ep.status == "completed"


def test_load_local_results_with_limit():
    """Test that limit parameter is respected."""
    fixtures_dir = SKILL_DIR / "test_fixtures"

    data = load_local_results(fixtures_dir, "test-policy", limit=2)

    assert len(data.episodes) == 2


def test_load_local_results_empty_directory():
    """Test handling of empty directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        data = load_local_results(Path(tmpdir), "empty-policy", limit=100)

        assert data.policy.name == "empty-policy"
        assert len(data.episodes) == 0


def test_load_local_results_skips_invalid_files():
    """Test that invalid JSON files are skipped."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Create a valid file
        valid = {"rewards": [1.0], "stats": {"game": {}, "agent": [{}]}, "steps": 100}
        (tmppath / "valid.json").write_text(json.dumps(valid))

        # Create an invalid file (missing required keys)
        invalid = {"foo": "bar"}
        (tmppath / "invalid.json").write_text(json.dumps(invalid))

        # Create a non-JSON file
        (tmppath / "readme.txt").write_text("not json")

        data = load_local_results(tmppath, "test", limit=100)

        assert len(data.episodes) == 1  # Only valid.json loaded


def test_data_to_dict():
    """Test DashboardData serialization."""
    policy = PolicyVersion(id="p1", name="test", version=1, rank=5, score=1.5, matches=10)
    episode = EpisodeData(
        episode_id="e1",
        job_id="j1",
        opponent_name="opp",
        opponent_version=2,
        team_composition="4v4",
        reward=10.5,
        status="completed",
        steps=5000,
        metrics={"a": 1.0},
    )
    data = DashboardData(
        policy=policy,
        episodes=[episode],
        season="test-season",
        generated_at="2024-01-01T00:00:00",
    )

    result = data_to_dict(data)

    assert result["policy"]["name"] == "test"
    assert result["policy"]["rank"] == 5
    assert len(result["episodes"]) == 1
    assert result["episodes"][0]["steps"] == 5000
    assert result["episodes"][0]["metrics"]["a"] == 1.0
    assert result["season"] == "test-season"


def test_generate_dashboard():
    """Test HTML dashboard generation."""
    policy = PolicyVersion(id="p1", name="test-policy", version=1)
    episodes = [
        EpisodeData(
            episode_id=f"e{i}",
            job_id="",
            opponent_name="none",
            opponent_version=0,
            team_composition="4v0",
            reward=float(i * 10),
            status="completed",
            steps=1000 * i,
            metrics={"action.move.success": float(i * 100)},
        )
        for i in range(1, 4)
    ]
    data = DashboardData(
        policy=policy,
        episodes=episodes,
        season="local",
        generated_at="2024-01-01T00:00:00",
    )

    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
        output_path = Path(f.name)

    try:
        generate_dashboard(data, output_path)

        html = output_path.read_text()

        # Verify dashboard contains expected data
        assert "test-policy" in html
        assert '"steps": 1000' in html or '"steps":1000' in html
        assert '"steps": 2000' in html or '"steps":2000' in html
        assert "action.move.success" in html
    finally:
        output_path.unlink()


def test_full_local_mode_pipeline():
    """End-to-end test: load fixtures, generate dashboard, verify output."""
    fixtures_dir = SKILL_DIR / "test_fixtures"

    # Load test data
    data = load_local_results(fixtures_dir, "integration-test", limit=100)

    # Generate dashboard
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
        output_path = Path(f.name)

    try:
        generate_dashboard(data, output_path)

        # Parse the generated JSON from HTML
        html = output_path.read_text()

        # Find and extract the JSON data
        idx = html.find('"policy"')
        start = html.rfind("{", 0, idx)
        depth = 0
        for i in range(start, len(html)):
            if html[i] == "{":
                depth += 1
            elif html[i] == "}":
                depth -= 1
            if depth == 0:
                json_str = html[start : i + 1]
                break

        dashboard_data = json.loads(json_str)

        # Verify structure
        assert dashboard_data["policy"]["name"] == "integration-test"
        assert len(dashboard_data["episodes"]) >= 3

        # Verify all episodes have required fields
        for ep in dashboard_data["episodes"]:
            assert "episode_id" in ep
            assert "reward" in ep
            assert "steps" in ep
            assert "metrics" in ep
            assert ep["steps"] > 0  # Fixtures should have non-zero steps

        # Verify metrics are populated
        total_metrics = sum(len(ep["metrics"]) for ep in dashboard_data["episodes"])
        assert total_metrics > 0

    finally:
        output_path.unlink()


def main():
    """Run all tests."""
    tests = [
        test_result_to_episode_data_basic,
        test_result_to_episode_data_with_opponent,
        test_result_to_episode_data_missing_steps,
        test_aggregate_agent_metrics,
        test_load_local_results,
        test_load_local_results_with_limit,
        test_load_local_results_empty_directory,
        test_load_local_results_skips_invalid_files,
        test_data_to_dict,
        test_generate_dashboard,
        test_full_local_mode_pipeline,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            print(f"✓ {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__}: {e}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
