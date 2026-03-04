from metta.trainingboard.models import AxisPanel, DashboardSnapshot, ResearchPaperRecord
from metta.trainingboard.scoring import build_dashboard_snapshot


def _panel(snapshot: DashboardSnapshot, axis_id: str) -> AxisPanel:
    return next(panel for panel in snapshot.ranked_axes if panel.axis_id == axis_id)


def test_dashboard_snapshot_contains_six_axes() -> None:
    snapshot = build_dashboard_snapshot([])
    assert len(snapshot.ranked_axes) == 6
    assert {panel.axis_id for panel in snapshot.ranked_axes} == {
        "experience_parallelism",
        "experience_quality",
        "loss_parallelism",
        "loss_signal_quality",
        "parameter_parallelism",
        "hyperparameter_quality",
    }


def test_experience_parallelism_multiplier_increases_with_relevant_evidence() -> None:
    baseline = build_dashboard_snapshot([])
    boosted = build_dashboard_snapshot(
        [
            ResearchPaperRecord(
                gid="paper-1",
                title="Scaling GPU actor rollout throughput",
                notes="We improved rollout actors and simulation parallelism using more GPUs.",
                permalink_url="https://example.com/paper-1",
                custom_fields={},
                paper_links=["https://arxiv.org/abs/1234.5678"],
                recommendations=["Recommendation: increase actor throughput across idle GPUs."],
                inferred_axis_scores={"experience_parallelism": 0.72},
            )
        ]
    )

    baseline_panel = _panel(baseline, "experience_parallelism")
    boosted_panel = _panel(boosted, "experience_parallelism")

    assert boosted_panel.evidence_count == 1
    assert boosted_panel.projected_multiplier > baseline_panel.projected_multiplier


def test_ranked_axes_are_sorted_by_opportunity_score_desc() -> None:
    snapshot = build_dashboard_snapshot([])
    scores = [panel.opportunity_score for panel in snapshot.ranked_axes]
    assert scores == sorted(scores, reverse=True)


def test_short_keyword_matches_token_boundary_only() -> None:
    snapshot = build_dashboard_snapshot(
        [
            ResearchPaperRecord(
                gid="paper-stddev",
                title="Rollout variance monitoring",
                notes="This report focuses on stddev drift and normalization only.",
                permalink_url="https://example.com/paper-stddev",
                custom_fields={},
                paper_links=[],
                recommendations=[],
                inferred_axis_scores={},
            )
        ]
    )

    loss_signal_panel = _panel(snapshot, "loss_signal_quality")
    assert loss_signal_panel.evidence_count == 0
