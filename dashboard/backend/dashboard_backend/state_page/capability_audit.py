"""Filesystem-backed capability checks for the dashboard capabilities tab."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from dashboard.backend.dashboard_backend.state_page.diagnostics import CapabilityCodeAudit, CapabilityCodeStatus

_REPO_ROOT = Path(__file__).resolve().parents[4]


@lru_cache(maxsize=128)
def _read_text(relative_path: str) -> str | None:
    path = _REPO_ROOT / relative_path
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


@lru_cache(maxsize=128)
def _read_ast(relative_path: str) -> ast.AST | None:
    content = _read_text(relative_path)
    if content is None:
        return None
    try:
        return ast.parse(content)
    except SyntaxError:
        return None


def _exists(relative_path: str) -> bool:
    return (_REPO_ROOT / relative_path).is_file()


def _has_python_function(relative_path: str, function_name: str) -> bool:
    tree = _read_ast(relative_path)
    if tree is None:
        return False
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name
        for node in ast.walk(tree)
    )


def _contains_all(relative_path: str, *tokens: str) -> bool:
    content = _read_text(relative_path)
    if content is None:
        return False
    return all(token in content for token in tokens)


def _status_from_checks(checks: list[tuple[str, str, bool]]) -> str:
    if not checks:
        return "planned"
    passing = sum(1 for _label, _ref, ok in checks if ok)
    if passing == len(checks):
        return "yes"
    if passing == 0:
        return "no"
    return "partial"


def _status_entry(training_source: str | None, checks: list[tuple[str, str, bool]]) -> CapabilityCodeStatus:
    evidence = [f"{'PASS' if ok else 'MISS'}: {label} [{ref}]" for label, ref, ok in checks]
    return CapabilityCodeStatus(
        status=_status_from_checks(checks),
        training_source=training_source,
        evidence=evidence,
    )


@lru_cache(maxsize=1)
def build_capability_code_audit() -> CapabilityCodeAudit:
    generated_at = datetime.now(timezone.utc).isoformat()

    capabilities = {
        "mining": _status_entry(
            "recipes/experiment/cogsguard.py::miner",
            [
                (
                    "role recipe function",
                    "recipes/experiment/cogsguard.py::miner",
                    _has_python_function("recipes/experiment/cogsguard.py", "miner"),
                ),
                (
                    "tutorial script",
                    "packages/cogames/tutorials/TRAIN_MINER.py",
                    _exists("packages/cogames/tutorials/TRAIN_MINER.py"),
                ),
                (
                    "tutorial mission registered",
                    "packages/cogames/src/cogames/cogs_vs_clips/missions.py",
                    _contains_all("packages/cogames/src/cogames/cogs_vs_clips/missions.py", "MinerTutorialMission"),
                ),
                (
                    "role-specific reward shaper",
                    "packages/cogames/src/cogames/cogs_vs_clips/reward_variants.py::_apply_miner",
                    _has_python_function(
                        "packages/cogames/src/cogames/cogs_vs_clips/reward_variants.py", "_apply_miner"
                    ),
                ),
            ],
        ),
        "aligning": _status_entry(
            "recipes/experiment/cogsguard.py::aligner",
            [
                (
                    "role recipe function",
                    "recipes/experiment/cogsguard.py::aligner",
                    _has_python_function("recipes/experiment/cogsguard.py", "aligner"),
                ),
                (
                    "tutorial script",
                    "packages/cogames/tutorials/TRAIN_ALIGNER.py",
                    _exists("packages/cogames/tutorials/TRAIN_ALIGNER.py"),
                ),
                (
                    "tutorial mission registered",
                    "packages/cogames/src/cogames/cogs_vs_clips/missions.py",
                    _contains_all("packages/cogames/src/cogames/cogs_vs_clips/missions.py", "AlignerTutorialMission"),
                ),
                (
                    "role-specific reward shaper",
                    "packages/cogames/src/cogames/cogs_vs_clips/reward_variants.py::_apply_aligner",
                    _has_python_function(
                        "packages/cogames/src/cogames/cogs_vs_clips/reward_variants.py", "_apply_aligner"
                    ),
                ),
            ],
        ),
        "scrambling": _status_entry(
            "recipes/experiment/cogsguard.py::scrambler",
            [
                (
                    "role recipe function",
                    "recipes/experiment/cogsguard.py::scrambler",
                    _has_python_function("recipes/experiment/cogsguard.py", "scrambler"),
                ),
                (
                    "scrambler tutorial mission",
                    "packages/cogames/src/cogames/cogs_vs_clips/scrambler_tutorial.py::ScramblerTutorialMission",
                    _contains_all(
                        "packages/cogames/src/cogames/cogs_vs_clips/scrambler_tutorial.py",
                        "ScramblerTutorialMission",
                        "ScramblerRewardsVariant",
                    ),
                ),
                (
                    "tutorial script",
                    "packages/cogames/tutorials/TRAIN_SCRAMBLER.py",
                    _exists("packages/cogames/tutorials/TRAIN_SCRAMBLER.py"),
                ),
                (
                    "tutorial mission registered",
                    "packages/cogames/src/cogames/cogs_vs_clips/missions.py",
                    _contains_all("packages/cogames/src/cogames/cogs_vs_clips/missions.py", "ScramblerTutorialMission"),
                ),
                (
                    "role-specific reward shaper",
                    "packages/cogames/src/cogames/cogs_vs_clips/reward_variants.py::_apply_scrambler",
                    _has_python_function(
                        "packages/cogames/src/cogames/cogs_vs_clips/reward_variants.py", "_apply_scrambler"
                    ),
                ),
            ],
        ),
        "scouting": _status_entry(
            "recipes/experiment/cogsguard.py::scout",
            [
                (
                    "role recipe function",
                    "recipes/experiment/cogsguard.py::scout",
                    _has_python_function("recipes/experiment/cogsguard.py", "scout"),
                ),
                (
                    "tutorial script",
                    "packages/cogames/tutorials/TRAIN_SCOUT.py",
                    _exists("packages/cogames/tutorials/TRAIN_SCOUT.py"),
                ),
                (
                    "tutorial mission registered",
                    "packages/cogames/src/cogames/cogs_vs_clips/missions.py",
                    _contains_all("packages/cogames/src/cogames/cogs_vs_clips/missions.py", "ScoutTutorialMission"),
                ),
                (
                    "role-specific reward shaper",
                    "packages/cogames/src/cogames/cogs_vs_clips/reward_variants.py::_apply_scout",
                    _has_python_function(
                        "packages/cogames/src/cogames/cogs_vs_clips/reward_variants.py", "_apply_scout"
                    ),
                ),
            ],
        ),
        "coordination": _status_entry(
            "recipes/experiment/coggernaut.py::train",
            [
                (
                    "integrated role training recipe",
                    "recipes/experiment/coggernaut.py::train",
                    _has_python_function("recipes/experiment/coggernaut.py", "train"),
                ),
                (
                    "all role ids wired",
                    "recipes/experiment/coggernaut.py::_ROLE_ORDER",
                    _contains_all(
                        "recipes/experiment/coggernaut.py",
                        "_ROLE_ORDER",
                        '"miner"',
                        '"aligner"',
                        '"scrambler"',
                        '"scout"',
                    ),
                ),
                (
                    "role-conditional reward shaping",
                    "packages/cogames/src/cogames/cogs_vs_clips/reward_variants.py",
                    _contains_all(
                        "packages/cogames/src/cogames/cogs_vs_clips/reward_variants.py", '"role_conditional"'
                    ),
                ),
                (
                    "two-policy coordination train recipe",
                    "recipes/experiment/cogsguard_marlbro.py::train",
                    _has_python_function("recipes/experiment/cogsguard_marlbro.py", "train"),
                ),
                (
                    "dedicated coordination tutorial",
                    "packages/cogames/tutorials/TRAIN_COORDINATION.py",
                    _exists("packages/cogames/tutorials/TRAIN_COORDINATION.py"),
                ),
            ],
        ),
    }

    sources = {
        "capability_eval": _status_entry(
            None,
            [
                (
                    "core role recipes available",
                    "recipes/experiment/cogsguard.py",
                    all(
                        _has_python_function("recipes/experiment/cogsguard.py", name)
                        for name in ("miner", "aligner", "scrambler", "scout")
                    ),
                ),
                (
                    "role reward variants available",
                    "packages/cogames/src/cogames/cogs_vs_clips/reward_variants.py",
                    _contains_all(
                        "packages/cogames/src/cogames/cogs_vs_clips/reward_variants.py",
                        '"miner"',
                        '"aligner"',
                        '"scrambler"',
                        '"scout"',
                    ),
                ),
            ],
        ),
        "cogames_axis": _status_entry(
            None,
            [
                (
                    "doctor-note endpoint",
                    "dashboard/backend/dashboard_backend/cogames_diagnose/router.py::get_doctor_note",
                    _has_python_function(
                        "dashboard/backend/dashboard_backend/cogames_diagnose/router.py", "get_doctor_note"
                    ),
                ),
                (
                    "axis fields in frontend schema",
                    "dashboard/frontend/src/lib/api.ts",
                    _contains_all("dashboard/frontend/src/lib/api.ts", "axes: DiagnoseAxisScore[]"),
                ),
            ],
        ),
        "cogames_probe": _status_entry(
            None,
            [
                (
                    "probe fields in frontend schema",
                    "dashboard/frontend/src/lib/api.ts",
                    _contains_all(
                        "dashboard/frontend/src/lib/api.ts",
                        "stage1_probe_catalog",
                        "stage1_probe_evaluations",
                    ),
                ),
                (
                    "probe card builder",
                    "dashboard/frontend/src/components/SkillTreePanel.tsx",
                    _contains_all("dashboard/frontend/src/components/SkillTreePanel.tsx", "buildDiagnoseProbeCards"),
                ),
            ],
        ),
        "cogames_symptom": _status_entry(
            None,
            [
                (
                    "symptom fields in frontend schema",
                    "dashboard/frontend/src/lib/api.ts",
                    _contains_all("dashboard/frontend/src/lib/api.ts", "symptoms: DiagnoseSymptom[]"),
                ),
                (
                    "symptom card builder",
                    "dashboard/frontend/src/components/SkillTreePanel.tsx",
                    _contains_all("dashboard/frontend/src/components/SkillTreePanel.tsx", "buildDiagnoseSymptomCards"),
                ),
            ],
        ),
        "kpi_diagnostic": _status_entry(
            None,
            [
                (
                    "derived KPI diagnostics generator",
                    "dashboard/backend/dashboard_backend/state_page/diagnostics.py::compute_derived_metrics",
                    _has_python_function(
                        "dashboard/backend/dashboard_backend/state_page/diagnostics.py", "compute_derived_metrics"
                    ),
                ),
                (
                    "kpi diagnostic cards in capabilities tab",
                    "dashboard/frontend/src/components/SkillTreePanel.tsx",
                    _contains_all("dashboard/frontend/src/components/SkillTreePanel.tsx", "buildKpiDiagnosticCards"),
                ),
            ],
        ),
        "instrumentation": _status_entry(
            None,
            [
                (
                    "instrumentation coverage computation",
                    "dashboard/backend/dashboard_backend/state_page/diagnostics.py::compute_instrumentation_validation",
                    _has_python_function(
                        "dashboard/backend/dashboard_backend/state_page/diagnostics.py",
                        "compute_instrumentation_validation",
                    ),
                ),
                (
                    "instrumentation summary included in dashboard response",
                    "dashboard/backend/dashboard_backend/state_page/router.py",
                    _contains_all(
                        "dashboard/backend/dashboard_backend/state_page/router.py",
                        "compute_instrumentation_validation(",
                    ),
                ),
                (
                    "instrumentation cards in capabilities tab",
                    "dashboard/frontend/src/components/SkillTreePanel.tsx",
                    _contains_all("dashboard/frontend/src/components/SkillTreePanel.tsx", "buildInstrumentationCards"),
                ),
            ],
        ),
        "behavior_slice": _status_entry(
            None,
            [
                (
                    "behavior tag computation",
                    "dashboard/backend/dashboard_backend/state_page/diagnostics.py::compute_episode_behavior_tags",
                    _has_python_function(
                        "dashboard/backend/dashboard_backend/state_page/diagnostics.py", "compute_episode_behavior_tags"
                    ),
                ),
                (
                    "behavior tags attached to episodes",
                    "dashboard/backend/dashboard_backend/state_page/episode_builder.py",
                    _contains_all(
                        "dashboard/backend/dashboard_backend/state_page/episode_builder.py",
                        "behavior_tags = compute_episode_behavior_tags",
                    ),
                ),
                (
                    "behavior slice cards in capabilities tab",
                    "dashboard/frontend/src/components/SkillTreePanel.tsx",
                    _contains_all("dashboard/frontend/src/components/SkillTreePanel.tsx", "buildBehaviorSliceCards"),
                ),
            ],
        ),
    }

    return CapabilityCodeAudit(
        generated_at=generated_at,
        capabilities=capabilities,
        sources=sources,
    )
