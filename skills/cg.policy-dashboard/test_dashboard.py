#!/usr/bin/env python3
"""Test suite for the policy dashboard.

Run before committing changes to validate dashboard functionality.
Uses local test fixtures in test_fixtures/ directory.
"""

from __future__ import annotations

import json
import re
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
    compute_derived_metrics,
    compute_team_comp_analysis,
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
                {"action.move.success": 100.0, "carbon.amount": 50.0},
                {"action.move.success": 120.0, "carbon.amount": 60.0},
                {"action.move.success": 80.0, "carbon.amount": 40.0},
                {"action.move.success": 110.0, "carbon.amount": 55.0},
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
    assert episode.metrics["carbon.amount"] == 205.0  # 50+60+40+55


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


def _make_episode(episode_id="e1", opponent="opp", reward=1.0, steps=1000, metrics=None, team_comp="4v4"):
    """Helper to create EpisodeData for tests."""
    return EpisodeData(
        episode_id=episode_id,
        job_id="j1",
        opponent_name=opponent,
        opponent_version=1,
        team_composition=team_comp,
        reward=reward,
        status="completed",
        steps=steps,
        metrics=metrics or {},
    )


# === Phase 1 Tests ===


def test_noop_rate_computation():
    """Test noop_rate = noop / total_actions."""
    episodes = [
        _make_episode(
            metrics={
                "action.noop.success": 100,
                "action.move.success": 800,
                "action.change_vibe.success": 50,
                "action.failed": 50,
            },
            steps=1000,
        ),
    ]
    derived = compute_derived_metrics(episodes)
    # noop_rate = 100 / (100 + 800 + 50 + 50) = 0.1
    assert abs(derived.noop_rate - 0.1) < 0.01


def test_resource_efficiency_per_step():
    """Test resource_efficiency_per_step = sum(gained) / total_steps."""
    episodes = [
        _make_episode(
            metrics={
                "carbon.gained": 50,
                "heart.gained": 10,
                "oxygen.gained": 20,
                "silicon.gained": 20,
                "germanium.gained": 0,
            },
            steps=1000,
        ),
    ]
    derived = compute_derived_metrics(episodes)
    # total_gained=100, total_steps=1000 -> 0.1
    assert abs(derived.resource_efficiency_per_step - 0.1) < 0.01


def test_hearts_to_junction_rate():
    """Test hearts_to_junction_rate, including heart.lost=0 edge case."""
    # Normal case
    episodes = [
        _make_episode(
            metrics={
                "junction.aligned_by_agent": 5,
                "heart.lost": 10,
            }
        ),
    ]
    derived = compute_derived_metrics(episodes)
    assert abs(derived.hearts_to_junction_rate - 0.5) < 0.01

    # Edge case: heart.lost = 0
    episodes = [_make_episode(metrics={"junction.aligned_by_agent": 5})]
    derived = compute_derived_metrics(episodes)
    assert derived.hearts_to_junction_rate == 0.0  # safe_div default


def test_reward_consistency():
    """Test reward consistency = 1 - (std/mean) clamped 0-1."""
    # All same reward => std=0, consistency=1.0
    episodes = [_make_episode(reward=2.0) for _ in range(5)]
    derived = compute_derived_metrics(episodes)
    assert abs(derived.reward_consistency - 1.0) < 0.01

    # High variance => low consistency
    episodes = [_make_episode(reward=r) for r in [0.1, 10.0, 0.1, 10.0, 0.1]]
    derived = compute_derived_metrics(episodes)
    assert derived.reward_consistency < 0.5


# === Phase 2 Tests ===


# === Phase 3 Tests ===


def test_diagnostic_high_noop():
    """Test high noop rate diagnostic triggers."""
    episodes = [
        _make_episode(
            metrics={
                "action.noop.success": 200,
                "action.move.success": 300,
                "action.change_vibe.success": 50,
                "action.failed": 50,
            }
        )
        for _ in range(10)
    ]
    derived = compute_derived_metrics(episodes)
    assert any("noop" in d.lower() for d in derived.diagnostics)


def test_diagnostic_matchup_disparity():
    """Test matchup disparity diagnostic triggers."""
    episodes = []
    # 5 episodes vs easy opponent with high reward
    for i in range(5):
        episodes.append(
            _make_episode(
                episode_id=f"easy-{i}",
                opponent="easy-bot",
                reward=5.0,
                metrics={"action.move.success": 100},
            )
        )
    # 5 episodes vs hard opponent with very low reward
    for i in range(5):
        episodes.append(
            _make_episode(
                episode_id=f"hard-{i}",
                opponent="hard-bot",
                reward=0.1,
                metrics={"action.move.success": 100},
            )
        )
    derived = compute_derived_metrics(episodes)
    assert any("matchup" in d.lower() or "disparity" in d.lower() for d in derived.diagnostics)


def test_diagnostic_declining_rewards():
    """Test declining rewards diagnostic triggers."""
    episodes = [
        _make_episode(episode_id=f"ep-{i}", reward=10.0 - i * 0.3, metrics={"action.move.success": 100})
        for i in range(30)
    ]
    derived = compute_derived_metrics(episodes)
    assert any("declining" in d.lower() for d in derived.diagnostics)


def test_diagnostic_frozen_low_reward():
    """Test high freeze + low reward diagnostic."""
    avg_reward = 5.0
    episodes = []
    # 5 normal episodes
    for i in range(5):
        episodes.append(
            _make_episode(
                episode_id=f"normal-{i}",
                reward=avg_reward,
                steps=1000,
                metrics={"status.frozen.ticks": 10, "action.move.success": 100},
            )
        )
    # 5 frozen + low reward episodes (frozen>15% AND reward<50% avg)
    for i in range(5):
        episodes.append(
            _make_episode(
                episode_id=f"frozen-{i}",
                reward=1.0,
                steps=1000,
                metrics={"status.frozen.ticks": 200, "action.move.success": 50},
            )
        )
    derived = compute_derived_metrics(episodes)
    assert any("freeze" in d.lower() or "frozen" in d.lower() for d in derived.diagnostics)


# === Phase 4 Tests ===


def test_team_comp_analysis():
    """Test team composition analysis groups correctly."""
    episodes = [
        _make_episode(team_comp="6v2", reward=3.0, metrics={"action.move.success": 100}),
        _make_episode(team_comp="6v2", reward=4.0, metrics={"action.move.success": 200}),
        _make_episode(team_comp="4v4", reward=2.0, metrics={"action.move.success": 150}),
        _make_episode(team_comp="2v6", reward=1.0, metrics={"action.move.success": 50}),
    ]
    comps = compute_team_comp_analysis(episodes)
    assert len(comps) >= 2
    comp_6v2 = next((c for c in comps if c.composition == "6v2"), None)
    assert comp_6v2 is not None
    assert comp_6v2.count == 2
    assert abs(comp_6v2.avg_reward - 3.5) < 0.01


def test_team_comp_red_flag():
    """Test over-reliance on agent count red flag."""
    episodes = []
    # 6v2: high reward
    for _i in range(5):
        episodes.append(_make_episode(team_comp="6v2", reward=10.0, metrics={"action.move.success": 100}))
    # 2v6: very low reward (ratio > 3.0)
    for _i in range(5):
        episodes.append(_make_episode(team_comp="2v6", reward=1.0, metrics={"action.move.success": 100}))
    derived = compute_derived_metrics(episodes)
    assert any("agent count" in d.lower() or "over-reliance" in d.lower() for d in derived.diagnostics)


def test_team_comp_missing_compositions():
    """Test handling of missing team compositions."""
    episodes = [
        _make_episode(team_comp="6v2", reward=5.0, metrics={"action.move.success": 100}),
    ]
    comps = compute_team_comp_analysis(episodes)
    assert len(comps) == 1
    assert comps[0].composition == "6v2"


# === Phase 5 Tests ===


def test_zero_count_detection():
    """Test zero-count capability detection."""
    episodes = [
        _make_episode(
            metrics={
                "junction.aligned_by_agent": 0,
                "junction.scrambled_by_agent": 0,
                "action.change_vibe.success": 10,
                "action.move.success": 100,
            }
        )
        for _ in range(5)
    ]
    derived = compute_derived_metrics(episodes)
    assert any("zero" in d.lower() or "unused" in d.lower() or "never" in d.lower() for d in derived.diagnostics)


def test_opponent_metrics_serialization():
    """Test per-opponent metrics appear in serialized data."""
    episodes = [
        _make_episode(opponent="bot-a", reward=3.0, metrics={"action.move.success": 100}),
        _make_episode(opponent="bot-a", reward=4.0, metrics={"action.move.success": 200}),
        _make_episode(opponent="bot-b", reward=1.0, metrics={"action.move.success": 50}),
    ]
    derived = compute_derived_metrics(episodes)
    data = DashboardData(
        policy=PolicyVersion(id="p1", name="t", version=1),
        episodes=episodes,
        season="test",
        generated_at="2024-01-01",
        derived=derived,
    )
    result = data_to_dict(data)
    assert "opponent_metrics" in result["derived"]
    assert "bot-a" in result["derived"]["opponent_metrics"]
    assert result["derived"]["opponent_metrics"]["bot-a"]["count"] == 2


def test_collective_stat_ingestion():
    """Test that collective stats are ingested with 'collective.' prefix."""
    result = {
        "rewards": [10.0, 12.0],
        "steps": 5000,
        "stats": {
            "game": {},
            "collective": {
                "carbon.deposited": 200.0,
                "aligned.junction.held": 500.0,
            },
            "agent": [
                {"action.move.success": 100.0},
                {"action.move.success": 120.0},
            ],
        },
    }
    assignments = [0, 0]

    episode = result_to_episode_data(
        result_dict=result,
        episode_id="test-coll",
        assignments=assignments,
        policy_index=0,
    )

    assert episode.metrics["collective.carbon.deposited"] == 200.0
    assert episode.metrics["collective.aligned.junction.held"] == 500.0
    # Agent metrics should still be present
    assert episode.metrics["action.move.success"] == 220.0


def test_game_stat_ingestion():
    """Test that game stats are ingested with 'game.' prefix."""
    result = {
        "rewards": [10.0],
        "steps": 5000,
        "stats": {
            "game": {
                "total_junctions": 12.0,
                "episode_length": 5000.0,
            },
            "agent": [
                {"action.move.success": 100.0},
            ],
        },
    }
    assignments = [0]

    episode = result_to_episode_data(
        result_dict=result,
        episode_id="test-game",
        assignments=assignments,
        policy_index=0,
    )

    assert episode.metrics["game.total_junctions"] == 12.0
    assert episode.metrics["game.episode_length"] == 5000.0
    # Agent metrics should still be present
    assert episode.metrics["action.move.success"] == 100.0


def test_high_low_comparison_metrics():
    """Test high/low comparison uses correct metric names."""
    # Verify the template references junction.aligned_by_agent not junction.aligned
    template_path = SKILL_DIR / "template.html"
    html = template_path.read_text()
    assert "junction.aligned_by_agent" in html
    # Should NOT have bare 'junction.aligned' in metric comparison (without _by_agent suffix)
    # The string 'junction.aligned' will appear as part of 'junction.aligned_by_agent' which is fine
    # Find junction.aligned that is NOT followed by _by_agent
    bare_refs = re.findall(r"junction\.aligned(?!_by_agent)", html)
    # Filter out any that are in aligned.junction (collective stats key)
    bare_refs = [r for r in bare_refs if r == "junction.aligned"]
    assert len(bare_refs) == 0, f"Found bare junction.aligned references: {bare_refs}"


def test_alignment_stability_formula():
    """Bug: alignment_stability divides by aligned_gained*100, should be just aligned_gained.

    If aligned_held=50 and aligned_gained=100, stability should be 0.5 (held/gained).
    The bug makes it 50/(100*100) = 0.005 instead.
    """
    episodes = [
        _make_episode(
            metrics={
                "junction.aligned_by_agent": 100,
                "aligned.junction.gained": 100,
                "aligned.junction.lost": 30,
                "aligned.junction.held": 50,
                "action.move.success": 500,
            }
        )
    ]
    derived = compute_derived_metrics(episodes)
    # held/gained = 50/100 = 0.5
    assert abs(derived.alignment_stability - 0.5) < 0.01, (
        f"alignment_stability should be 0.5 (held/gained), got {derived.alignment_stability}"
    )


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
        # Phase 1
        test_noop_rate_computation,
        test_resource_efficiency_per_step,
        test_hearts_to_junction_rate,
        test_reward_consistency,
        # Phase 3
        test_diagnostic_high_noop,
        test_diagnostic_matchup_disparity,
        test_diagnostic_declining_rewards,
        test_diagnostic_frozen_low_reward,
        # Phase 4
        test_team_comp_analysis,
        test_team_comp_red_flag,
        test_team_comp_missing_compositions,
        # Phase 5
        test_zero_count_detection,
        test_opponent_metrics_serialization,
        test_high_low_comparison_metrics,
        # Phase 6 - collective/game stats
        test_collective_stat_ingestion,
        test_game_stat_ingestion,
        # Bug regression tests
        test_alignment_stability_formula,
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
