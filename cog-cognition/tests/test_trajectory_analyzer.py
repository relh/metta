from __future__ import annotations

from cog_cognition.analysis import analyze_cogsguard_policy as exported_analyze_cogsguard_policy
from cog_cognition.analysis.trajectory import (
    AgentMotifSummary,
    ResourceVector,
    RoleCounts,
    RoleDistanceSummary,
    TrajectoryCheckpoint,
    TrajectoryMilestones,
    TrajectoryReport,
    _aligner_target_overlap,
    _derive_cogsguard_insights,
    analyze_cogsguard_policy,
)

from mettagrid.policy.policy import PolicySpec


def test_analysis_package_exports_trajectory_analyzer() -> None:
    assert exported_analyze_cogsguard_policy is analyze_cogsguard_policy


def test_analyze_cogsguard_policy_returns_live_checkpoints() -> None:
    report = analyze_cogsguard_policy(
        mission_name="machina_1",
        policy_spec=PolicySpec(class_path="cog_cyborg.policy.semantic_cog.MettagridSemanticPolicy"),
        cogs=8,
        steps=40,
        seed=42,
        sample_every=20,
    )

    assert report.steps == 40
    assert [checkpoint.step for checkpoint in report.checkpoints] == [1, 20, 40]
    assert report.checkpoints[-1].aligned_junction_held >= 0.0
    assert report.milestones.first_miner_gear_step is not None
    assert report.plateau_step is None or report.plateau_step <= report.steps


def test_derive_cogsguard_insights_flags_economy_then_control_gap() -> None:
    report = TrajectoryReport(
        policy_name="test",
        mission_name="machina_1",
        seed=42,
        steps=1000,
        avg_reward_per_agent=4.0,
        avg_deaths_per_agent=1.0,
        final_aligned_junctions=8,
        final_aligned_junction_held=10_000.0,
        final_enemy_aligned_junction_held=30_000.0,
        milestones=TrajectoryMilestones(),
        checkpoints=[
            TrajectoryCheckpoint(
                step=250,
                avg_reward_per_agent=1.0,
                aligned_junctions=2,
                aligned_junctions_gained=3,
                aligned_junction_held=1_000.0,
                enemy_aligned_junction_held=5_000.0,
                control_per_heart_withdrawn=0.0,
                effective_heart_gains=0,
                effective_heart_spends=0,
                control_per_alignment_gain=333.0,
                team_inventory=ResourceVector(carbon=20, oxygen=20, germanium=20, silicon=20),
                team_deposits=ResourceVector(carbon=50, oxygen=50, germanium=50, silicon=50),
                team_withdrawals=ResourceVector(),
                equipped_roles=RoleCounts(miner=2, aligner=6),
                declared_roles=RoleCounts(miner=2, aligner=6),
                role_max_hub_distance=RoleDistanceSummary(miner=12, aligner=14),
                carrying_hearts=0,
                carrying_resources=10,
                stationary_agents=0,
                max_stationary_streak=0,
                far_enemy_junctions_seen=0,
                far_neutral_junctions_seen=0,
                best_frontier_coverage=1,
                heart_supply_capacity=1,
                pressure_budget=3,
                pressure_oversubscription=3,
            ),
            TrajectoryCheckpoint(
                step=1000,
                avg_reward_per_agent=4.0,
                aligned_junctions=8,
                aligned_junctions_gained=12,
                aligned_junction_held=10_000.0,
                enemy_aligned_junction_held=30_000.0,
                control_per_heart_withdrawn=2_000.0,
                effective_heart_gains=40,
                effective_heart_spends=32,
                control_per_heart_gain=250.0,
                control_per_heart_spend=312.5,
                control_per_alignment_gain=333.0,
                team_inventory=ResourceVector(carbon=300, oxygen=300, germanium=300, silicon=300),
                team_deposits=ResourceVector(carbon=800, oxygen=800, germanium=800, silicon=800),
                team_withdrawals=ResourceVector(heart=5),
                equipped_roles=RoleCounts(miner=3, aligner=5),
                declared_roles=RoleCounts(miner=3, aligner=5),
                role_max_hub_distance=RoleDistanceSummary(miner=18, aligner=22),
                carrying_hearts=1,
                carrying_resources=20,
                stationary_agents=2,
                max_stationary_streak=24,
                far_enemy_junctions_seen=4,
                far_neutral_junctions_seen=2,
                best_frontier_coverage=4,
                best_enemy_scramble_block=3,
                heart_supply_capacity=2,
                pressure_budget=4,
                pressure_oversubscription=1,
                cumulative_risky_low_hp_steps=30,
            ),
        ],
    )

    insights = _derive_cogsguard_insights(report)

    assert any("Opening pressure is overcommitted to aligners" in insight for insight in insights)
    assert any("Early pressure roles exceed the budget" in insight for insight in insights)
    assert any("each spent heart is producing too little control" in insight for insight in insights)
    assert any("Heart-to-control efficiency is low" in insight for insight in insights)
    assert any("Late pressure demand still exceeds the economy-backed budget" in insight for insight in insights)
    assert any("target selection is still too distance-biased" in insight for insight in insights)
    assert any("blocking large neutral regions" in insight for insight in insights)
    assert any("Far enemy junctions are being discovered" in insight for insight in insights)
    assert any("deaths are likely preventable" in insight for insight in insights)
    assert any("Long stationary streaks remain a material control issue" in insight for insight in insights)


def test_aligner_target_overlap_counts_duplicate_intents() -> None:
    collisions, unique_targets = _aligner_target_overlap(
        {
            0: {"role": "aligner", "summary": "align_junction", "target_position": "5,0"},
            1: {"role": "aligner", "summary": "align_junction", "target_position": "5,0"},
            2: {"role": "aligner", "summary": "align_junction", "target_position": "6,0"},
            3: {"role": "miner", "summary": "mine_carbon", "target_position": "5,0"},
        }
    )

    assert collisions == 1
    assert unique_targets == 2


def test_derive_cogsguard_insights_flags_target_churn() -> None:
    report = TrajectoryReport(
        policy_name="test",
        mission_name="machina_1",
        seed=42,
        steps=1000,
        avg_reward_per_agent=5.0,
        final_aligned_junctions=12,
        final_aligned_junction_held=15_000.0,
        final_enemy_aligned_junction_held=16_000.0,
        checkpoints=[
            TrajectoryCheckpoint(
                step=1000,
                avg_reward_per_agent=5.0,
                aligned_junctions=12,
                aligned_junctions_gained=16,
                aligned_junction_held=15_000.0,
                enemy_aligned_junction_held=16_000.0,
                control_per_heart_withdrawn=500.0,
                effective_heart_gains=40,
                effective_heart_spends=35,
                control_per_heart_gain=375.0,
                control_per_heart_spend=428.5,
                control_per_alignment_gain=400.0,
                team_inventory=ResourceVector(carbon=40, oxygen=40, germanium=40, silicon=40),
                team_deposits=ResourceVector(carbon=300, oxygen=300, germanium=300, silicon=300),
                team_withdrawals=ResourceVector(),
                equipped_roles=RoleCounts(miner=3, aligner=5),
                declared_roles=RoleCounts(miner=3, aligner=5),
                role_max_hub_distance=RoleDistanceSummary(miner=12, aligner=25),
                carrying_hearts=3,
                carrying_resources=5,
                stationary_agents=1,
                max_stationary_streak=6,
                far_enemy_junctions_seen=3,
                far_neutral_junctions_seen=5,
            )
        ],
        agent_motifs=[
            AgentMotifSummary(
                agent_id=4,
                declared_role="aligner",
                target_switches=18,
                target_abandonments=10,
                target_progress_steps=12,
                target_regress_steps=9,
                target_stall_steps=14,
            )
        ],
    )

    insights = _derive_cogsguard_insights(report)

    assert any("Target pursuit is churning" in insight for insight in insights)
    assert any("approach steps are not reliably making progress" in insight for insight in insights)


def test_derive_cogsguard_insights_flags_role_flapping() -> None:
    report = TrajectoryReport(
        policy_name="test",
        mission_name="machina_1",
        seed=42,
        steps=1000,
        avg_reward_per_agent=5.0,
        final_aligned_junctions=12,
        final_aligned_junction_held=15_000.0,
        final_enemy_aligned_junction_held=16_000.0,
        checkpoints=[
            TrajectoryCheckpoint(
                step=1000,
                avg_reward_per_agent=5.0,
                aligned_junctions=12,
                aligned_junctions_gained=16,
                aligned_junction_held=15_000.0,
                enemy_aligned_junction_held=16_000.0,
                control_per_heart_withdrawn=500.0,
                effective_heart_gains=40,
                effective_heart_spends=35,
                control_per_heart_gain=375.0,
                control_per_heart_spend=428.5,
                control_per_alignment_gain=400.0,
                team_inventory=ResourceVector(carbon=40, oxygen=40, germanium=40, silicon=40),
                team_deposits=ResourceVector(carbon=300, oxygen=300, germanium=300, silicon=300),
                team_withdrawals=ResourceVector(),
                equipped_roles=RoleCounts(miner=3, aligner=5),
                declared_roles=RoleCounts(miner=3, aligner=5),
                role_max_hub_distance=RoleDistanceSummary(miner=12, aligner=25),
                carrying_hearts=3,
                carrying_resources=5,
                stationary_agents=1,
                max_stationary_streak=6,
                far_enemy_junctions_seen=3,
                far_neutral_junctions_seen=5,
            )
        ],
        agent_motifs=[
            AgentMotifSummary(agent_id=3, declared_role="aligner", role_switches=5),
            AgentMotifSummary(agent_id=4, declared_role="miner", role_switches=2),
        ],
    )

    insights = _derive_cogsguard_insights(report)

    assert any("Declared roles are flapping" in insight for insight in insights)


def test_derive_cogsguard_insights_flags_supply_blocked_regear_and_payload_loss() -> None:
    report = TrajectoryReport(
        policy_name="test",
        mission_name="machina_1",
        seed=42,
        steps=10_000,
        avg_reward_per_agent=6.0,
        avg_deaths_per_agent=1.0,
        final_aligned_junctions=20,
        final_aligned_junction_held=80_000.0,
        final_enemy_aligned_junction_held=100_000.0,
        checkpoints=[
            TrajectoryCheckpoint(
                step=10_000,
                avg_reward_per_agent=6.0,
                aligned_junctions=20,
                aligned_junctions_gained=100,
                aligned_junction_held=80_000.0,
                enemy_aligned_junction_held=100_000.0,
                control_per_heart_withdrawn=400.0,
                effective_heart_gains=200,
                effective_heart_spends=190,
                control_per_heart_gain=400.0,
                control_per_heart_spend=421.0,
                control_per_alignment_gain=800.0,
                team_inventory=ResourceVector(carbon=5, oxygen=5, germanium=5, silicon=5),
                team_deposits=ResourceVector(carbon=800, oxygen=800, germanium=800, silicon=800),
                team_withdrawals=ResourceVector(heart=5),
                equipped_roles=RoleCounts(miner=1, aligner=1, scrambler=0, unknown=6),
                declared_roles=RoleCounts(miner=3, aligner=3, scrambler=2),
                role_max_hub_distance=RoleDistanceSummary(miner=15, aligner=20, scrambler=45),
                carrying_hearts=2,
                carrying_resources=8,
                stationary_agents=1,
                max_stationary_streak=4,
                far_enemy_junctions_seen=10,
                far_neutral_junctions_seen=1,
                gearless_unaffordable_agents=3,
                heart_starved_agents=2,
                payload_risk_agents=2,
                cumulative_payload_risk_steps=250,
                cumulative_risky_low_hp_steps=200,
            )
        ],
        agent_motifs=[
            AgentMotifSummary(
                agent_id=4,
                declared_role="aligner",
                gearless_unaffordable_steps=250,
                heart_starved_steps=120,
                payload_risk_steps=140,
                payload_loss_events=4,
                payload_loss_hearts=6,
                payload_loss_resources=28,
            )
        ],
    )

    insights = _derive_cogsguard_insights(report)

    assert any("supply-blocked" in insight for insight in insights)
    assert any("supply starvation" in insight for insight in insights)
    assert any("payload" in insight for insight in insights)
