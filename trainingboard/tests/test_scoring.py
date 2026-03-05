from metta.trainingboard.models import (
    AxisPanel,
    DashboardSnapshot,
    LLMTaskScores,
    RankedTask,
    ResearchPaperRecord,
    TaskExecutionScores,
    TaskRankingSnapshot,
)
from metta.trainingboard.scoring import build_dashboard_snapshot, build_task_leaderboards, build_task_ranking_snapshot


def _panel(snapshot: DashboardSnapshot, axis_id: str) -> AxisPanel:
    return next(panel for panel in snapshot.ranked_axes if panel.axis_id == axis_id)


def _ranked_task(snapshot: TaskRankingSnapshot, gid: str) -> RankedTask:
    return next(task for task in snapshot.ranked_tasks if task.gid == gid)


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
    assert boosted_panel.opportunity_score > baseline_panel.opportunity_score


def test_ranked_axes_keep_fixed_axis_order() -> None:
    snapshot = build_dashboard_snapshot([])
    indices = [panel.index for panel in snapshot.ranked_axes]
    assert indices == [1, 2, 3, 4, 5, 6]


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


def test_dashboard_snapshot_uses_llm_axis_scores_without_heuristic_fallback() -> None:
    llm_scores = LLMTaskScores(
        axis_scores={
            "experience_parallelism": 0.91,
            "experience_quality": 0.0,
            "loss_parallelism": 0.0,
            "loss_signal_quality": 0.0,
            "parameter_parallelism": 0.0,
            "hyperparameter_quality": 0.0,
        },
        execution_scores=TaskExecutionScores(
            simplicity=0.6,
            time_to_implement=0.6,
            failure_likelihood=0.3,
            dependency_load=0.2,
            measurement_speed=0.6,
            reversibility=0.6,
        ),
        evidence_confidence=0.8,
        rationale="",
    )
    papers = [
        ResearchPaperRecord(
            gid="task-llm-only",
            title="Opaque proposal",
            notes="",
            permalink_url="https://example.com/task-llm-only",
            custom_fields={},
            paper_links=[],
            recommendations=[],
            inferred_axis_scores={},
        ),
        ResearchPaperRecord(
            gid="task-fallback",
            title="Fallback actor throughput candidate",
            notes="",
            permalink_url="https://example.com/task-fallback",
            custom_fields={},
            paper_links=[],
            recommendations=[],
            inferred_axis_scores={"experience_parallelism": 0.62},
        ),
    ]
    heuristic_snapshot = build_dashboard_snapshot(papers)
    llm_snapshot = build_dashboard_snapshot(papers, llm_scores_by_gid={"task-llm-only": llm_scores})

    heuristic_panel = _panel(heuristic_snapshot, "experience_parallelism")
    llm_panel = _panel(llm_snapshot, "experience_parallelism")
    assert heuristic_panel.evidence_count == 1
    assert llm_panel.evidence_count == 1
    assert "Opaque proposal" in llm_panel.evidence_titles
    assert "Fallback actor throughput candidate" not in llm_panel.evidence_titles


def test_task_ranking_contains_twelve_metrics() -> None:
    snapshot = build_task_ranking_snapshot(
        [
            ResearchPaperRecord(
                gid="task-1",
                title="Increase rollout actor throughput with better GPU parallelism",
                notes="Small bug fix plus logging for actor throughput benchmark.",
                permalink_url="https://example.com/task-1",
                custom_fields={"Complexity": "Low"},
                paper_links=["https://arxiv.org/abs/1234.5678"],
                recommendations=["Use a quick instrumentation pass to validate wall-clock gain."],
                inferred_axis_scores={"experience_parallelism": 0.68},
            )
        ],
        limit=5,
    )

    ranked_task = snapshot.ranked_tasks[0]
    assert snapshot.tasks_scored == 1
    assert len(snapshot.impact_metrics) == 6
    assert len(snapshot.execution_metrics) == 6
    assert set(ranked_task.axis_scores.keys()) == {
        "experience_parallelism",
        "experience_quality",
        "loss_parallelism",
        "loss_signal_quality",
        "parameter_parallelism",
        "hyperparameter_quality",
    }
    assert set(ranked_task.execution_scores.model_dump().keys()) == {
        "simplicity",
        "time_to_implement",
        "failure_likelihood",
        "dependency_load",
        "measurement_speed",
        "reversibility",
    }
    assert all(0.0 <= value <= 1.0 for value in ranked_task.axis_scores.values())
    assert all(0.0 <= value <= 1.0 for value in ranked_task.execution_scores.model_dump().values())


def test_task_ranking_prefers_high_feasibility_when_impact_is_similar() -> None:
    snapshot = build_task_ranking_snapshot(
        [
            ResearchPaperRecord(
                gid="task-feasible",
                title="GPU actor throughput logging fix",
                notes="Quick bug fix with incremental config change and direct benchmark metric.",
                permalink_url="https://example.com/task-feasible",
                custom_fields={"Complexity": "Low"},
                paper_links=[],
                recommendations=[],
                inferred_axis_scores={"experience_parallelism": 0.65},
            ),
            ResearchPaperRecord(
                gid="task-risky",
                title="Distributed GPU actor rewrite",
                notes="Novel from-scratch distributed architecture migration with API integration.",
                permalink_url="https://example.com/task-risky",
                custom_fields={"Complexity": "High"},
                paper_links=[],
                recommendations=[],
                inferred_axis_scores={"experience_parallelism": 0.66},
            ),
        ],
        limit=5,
    )

    feasible_task = _ranked_task(snapshot, "task-feasible")
    risky_task = _ranked_task(snapshot, "task-risky")
    assert feasible_task.feasibility_score > risky_task.feasibility_score
    assert feasible_task.execution_scores.failure_likelihood < risky_task.execution_scores.failure_likelihood
    assert snapshot.ranked_tasks[0].gid == "task-feasible"


def test_task_ranking_limit_applies() -> None:
    snapshot = build_task_ranking_snapshot(
        [
            ResearchPaperRecord(
                gid=f"task-{index}",
                title=f"Task {index}",
                notes="",
                permalink_url=f"https://example.com/task-{index}",
                custom_fields={},
                paper_links=[],
                recommendations=[],
                inferred_axis_scores={},
            )
            for index in range(3)
        ],
        limit=2,
    )
    assert snapshot.tasks_scored == 3
    assert len(snapshot.ranked_tasks) == 2


def test_task_ranking_uses_llm_scores_when_provided() -> None:
    llm_scores = LLMTaskScores(
        axis_scores={
            "experience_parallelism": 0.91,
            "experience_quality": 0.12,
            "loss_parallelism": 0.18,
            "loss_signal_quality": 0.22,
            "parameter_parallelism": 0.35,
            "hyperparameter_quality": 0.14,
        },
        execution_scores=TaskExecutionScores(
            simplicity=0.8,
            time_to_implement=0.78,
            failure_likelihood=0.2,
            dependency_load=0.15,
            measurement_speed=0.73,
            reversibility=0.76,
        ),
        evidence_confidence=0.87,
        rationale="Focused GPU throughput proposal with clear validation path.",
    )
    snapshot = build_task_ranking_snapshot(
        [
            ResearchPaperRecord(
                gid="task-llm",
                title="Placeholder",
                notes="",
                permalink_url="https://example.com/task-llm",
                custom_fields={},
                paper_links=[],
                recommendations=[],
                inferred_axis_scores={},
            )
        ],
        limit=5,
        llm_scores_by_gid={"task-llm": llm_scores},
    )

    ranked_task = snapshot.ranked_tasks[0]
    assert ranked_task.axis_scores["experience_parallelism"] == 0.91
    assert ranked_task.execution_scores.simplicity == 0.8
    assert ranked_task.evidence_confidence == 0.87


def test_task_ranking_can_require_llm_scores() -> None:
    llm_scores = LLMTaskScores(
        axis_scores={
            "experience_parallelism": 0.91,
            "experience_quality": 0.12,
            "loss_parallelism": 0.18,
            "loss_signal_quality": 0.22,
            "parameter_parallelism": 0.35,
            "hyperparameter_quality": 0.14,
        },
        execution_scores=TaskExecutionScores(
            simplicity=0.8,
            time_to_implement=0.78,
            failure_likelihood=0.2,
            dependency_load=0.15,
            measurement_speed=0.73,
            reversibility=0.76,
        ),
        evidence_confidence=0.87,
        rationale="",
    )
    snapshot = build_task_ranking_snapshot(
        [
            ResearchPaperRecord(
                gid="task-llm",
                title="LLM scored",
                notes="",
                permalink_url="https://example.com/task-llm",
                custom_fields={},
                paper_links=[],
                recommendations=[],
                inferred_axis_scores={},
            ),
            ResearchPaperRecord(
                gid="task-no-llm",
                title="No LLM score",
                notes="",
                permalink_url="https://example.com/task-no-llm",
                custom_fields={},
                paper_links=[],
                recommendations=[],
                inferred_axis_scores={"experience_parallelism": 0.9},
            ),
        ],
        llm_scores_by_gid={"task-llm": llm_scores},
        require_llm_scores=True,
    )
    assert snapshot.tasks_scored == 1
    assert len(snapshot.ranked_tasks) == 1
    assert snapshot.ranked_tasks[0].gid == "task-llm"


def test_task_ranking_dedupes_replicate_titles() -> None:
    snapshot = build_task_ranking_snapshot(
        [
            ResearchPaperRecord(
                gid="task-ada",
                title="Ada",
                notes="",
                permalink_url="https://example.com/task-ada",
                custom_fields={},
                paper_links=[],
                recommendations=[],
                inferred_axis_scores={"experience_quality": 0.9},
            ),
            ResearchPaperRecord(
                gid="task-replicate-ada",
                title="Replicate Ada",
                notes="",
                permalink_url="https://example.com/task-replicate-ada",
                custom_fields={},
                paper_links=[],
                recommendations=[],
                inferred_axis_scores={"experience_quality": 0.85},
            ),
        ],
        limit=10,
    )

    gids = [task.gid for task in snapshot.ranked_tasks]
    assert "task-ada" in gids
    assert "task-replicate-ada" not in gids


def test_task_ranking_can_disable_title_dedup() -> None:
    snapshot = build_task_ranking_snapshot(
        [
            ResearchPaperRecord(
                gid="task-ada",
                title="Ada",
                notes="",
                permalink_url="https://example.com/task-ada",
                custom_fields={},
                paper_links=[],
                recommendations=[],
                inferred_axis_scores={"experience_quality": 0.9},
            ),
            ResearchPaperRecord(
                gid="task-replicate-ada",
                title="Replicate Ada",
                notes="",
                permalink_url="https://example.com/task-replicate-ada",
                custom_fields={},
                paper_links=[],
                recommendations=[],
                inferred_axis_scores={"experience_quality": 0.85},
            ),
        ],
        limit=10,
        dedupe_titles=False,
    )

    gids = [task.gid for task in snapshot.ranked_tasks]
    assert "task-ada" in gids
    assert "task-replicate-ada" in gids


def test_task_leaderboards_include_overall_and_axis_lists() -> None:
    snapshot = build_task_ranking_snapshot(
        [
            ResearchPaperRecord(
                gid="task-1",
                title="GPU actor throughput",
                notes="parallel rollout and learner throughput",
                permalink_url="https://example.com/task-1",
                custom_fields={},
                paper_links=[],
                recommendations=[],
                inferred_axis_scores={"experience_parallelism": 0.9},
            ),
            ResearchPaperRecord(
                gid="task-2",
                title="Curriculum scheduler",
                notes="adaptive curriculum map selection",
                permalink_url="https://example.com/task-2",
                custom_fields={},
                paper_links=[],
                recommendations=[],
                inferred_axis_scores={"experience_quality": 0.8},
            ),
        ],
        limit=None,
    )
    leaderboards = build_task_leaderboards(snapshot.ranked_tasks, top_n=1)

    assert len(leaderboards["top_overall"]) == 1
    top_by_axis = leaderboards["top_by_axis"]
    assert "experience_parallelism" in top_by_axis
    assert "experience_quality" in top_by_axis
    assert len(top_by_axis["experience_parallelism"]) == 1
