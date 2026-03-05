"""Filesystem-backed capability checks for the dashboard capabilities tab."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from vibeservatory.backend.dashboard_backend.state_page.diagnostics import CapabilityCodeAudit, CapabilityCodeStatus

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SKIP_DIR_NAMES = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
_TEXT_SUFFIXES = (".py", ".md", ".toml", ".yaml", ".yml")


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


@lru_cache(maxsize=64)
def _iter_relative_files(roots: tuple[str, ...], suffixes: tuple[str, ...]) -> tuple[str, ...]:
    relative_files: set[str] = set()
    for root in roots:
        candidate = (_REPO_ROOT / root).resolve()
        if not candidate.exists():
            continue
        if candidate.is_file():
            if not suffixes or candidate.suffix in suffixes:
                relative_files.add(str(candidate.relative_to(_REPO_ROOT)))
            continue
        relative_files.update(
            str(path.relative_to(_REPO_ROOT))
            for path in candidate.rglob("*")
            if path.is_file()
            and not any(part in _SKIP_DIR_NAMES for part in path.parts)
            and (not suffixes or path.suffix in suffixes)
        )
    return tuple(sorted(relative_files))


@lru_cache(maxsize=256)
def _keyword_hits(
    roots: tuple[str, ...], tokens: tuple[str, ...], suffixes: tuple[str, ...] = _TEXT_SUFFIXES
) -> tuple[str, ...]:
    normalized_tokens = tuple(token.strip().lower() for token in tokens if token.strip())
    if not normalized_tokens:
        return tuple()
    matches: list[str] = []
    for relative_path in _iter_relative_files(roots, suffixes):
        content = _read_text(relative_path)
        if content is None:
            continue
        lowered = content.lower()
        if all(token in lowered for token in normalized_tokens):
            matches.append(relative_path)
    return tuple(matches)


def _keyword_check(label: str, roots: tuple[str, ...], tokens: tuple[str, ...]) -> tuple[str, str, bool]:
    hits = _keyword_hits(roots, tokens)
    if hits:
        return label, hits[0], True
    root_desc = ", ".join(roots)
    token_desc = " & ".join(tokens)
    return label, f"keyword search in {root_desc}: {token_desc}", False


def _status_from_checks(checks: list[tuple[str, str, bool]]) -> str:
    if not checks:
        return "planned"
    passing = sum(1 for _label, _ref, ok in checks if ok)
    if passing == len(checks):
        return "yes"
    if passing == 0:
        return "no"
    return "partial"


def _status_entry(
    training_source: str | None,
    checks: list[tuple[str, str, bool]],
    *,
    support_type: str = "backed",
) -> CapabilityCodeStatus:
    evidence = [f"{'PASS' if ok else 'MISS'}: {label} [{ref}]" for label, ref, ok in checks]
    return CapabilityCodeStatus(
        status=_status_from_checks(checks),
        support_type=support_type,
        training_source=training_source,
        evidence=evidence,
    )


@lru_cache(maxsize=1)
def build_capability_code_audit() -> CapabilityCodeAudit:
    generated_at = datetime.now(timezone.utc).isoformat()
    reward_variants_file = "packages/cogames/src/cogames/cogs_vs_clips/reward_variants.py"
    mining_shaper_exists = _has_python_function(reward_variants_file, "_apply_miner")
    aligning_shaper_exists = _has_python_function(reward_variants_file, "_apply_aligner")
    scrambling_shaper_exists = _has_python_function(reward_variants_file, "_apply_scrambler")
    scouting_shaper_exists = _has_python_function(reward_variants_file, "_apply_scout")
    coordination_shaper_exists = _contains_all(reward_variants_file, '"role_conditional"')

    capabilities = {
        "mining": _status_entry(
            "recipes/experiment/cogsguard.py::miner",
            [
                (
                    "role recipe function",
                    "recipes/experiment/cogsguard.py::miner",
                    _has_python_function("recipes/experiment/cogsguard.py", "miner"),
                ),
                _keyword_check(
                    "tutorial coverage (keyword discovery)",
                    ("packages/cogames/tutorials", "packages/cogames/src/cogames/cogs_vs_clips"),
                    ("miner_tutorial", "minerrewardsvariant"),
                ),
                (
                    "role-specific reward shaper",
                    "packages/cogames/src/cogames/cogs_vs_clips/reward_variants.py::_apply_miner",
                    mining_shaper_exists,
                ),
            ],
            support_type="trained" if mining_shaper_exists else "backed",
        ),
        "aligning": _status_entry(
            "recipes/experiment/cogsguard.py::aligner",
            [
                (
                    "role recipe function",
                    "recipes/experiment/cogsguard.py::aligner",
                    _has_python_function("recipes/experiment/cogsguard.py", "aligner"),
                ),
                _keyword_check(
                    "tutorial coverage (keyword discovery)",
                    ("packages/cogames/tutorials", "packages/cogames/src/cogames/cogs_vs_clips"),
                    ("aligner_tutorial", "alignerrewardsvariant"),
                ),
                (
                    "role-specific reward shaper",
                    "packages/cogames/src/cogames/cogs_vs_clips/reward_variants.py::_apply_aligner",
                    aligning_shaper_exists,
                ),
            ],
            support_type="trained" if aligning_shaper_exists else "backed",
        ),
        "scrambling": _status_entry(
            "recipes/experiment/cogsguard.py::scrambler",
            [
                (
                    "role recipe function",
                    "recipes/experiment/cogsguard.py::scrambler",
                    _has_python_function("recipes/experiment/cogsguard.py", "scrambler"),
                ),
                _keyword_check(
                    "tutorial coverage (keyword discovery)",
                    ("packages/cogames/tutorials", "packages/cogames/src/cogames/cogs_vs_clips"),
                    ("scrambler_tutorial", "scramblerrewardsvariant"),
                ),
                (
                    "role-specific reward shaper",
                    "packages/cogames/src/cogames/cogs_vs_clips/reward_variants.py::_apply_scrambler",
                    scrambling_shaper_exists,
                ),
            ],
            support_type="trained" if scrambling_shaper_exists else "backed",
        ),
        "scouting": _status_entry(
            "recipes/experiment/cogsguard.py::scout",
            [
                (
                    "role recipe function",
                    "recipes/experiment/cogsguard.py::scout",
                    _has_python_function("recipes/experiment/cogsguard.py", "scout"),
                ),
                _keyword_check(
                    "tutorial coverage (keyword discovery)",
                    ("packages/cogames/tutorials", "packages/cogames/src/cogames/cogs_vs_clips"),
                    ("scout_tutorial", "scoutrewardsvariant"),
                ),
                (
                    "role-specific reward shaper",
                    "packages/cogames/src/cogames/cogs_vs_clips/reward_variants.py::_apply_scout",
                    scouting_shaper_exists,
                ),
            ],
            support_type="trained" if scouting_shaper_exists else "backed",
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
                    coordination_shaper_exists,
                ),
                (
                    "two-policy coordination train recipe",
                    "recipes/experiment/cogsguard_marlbro.py::train",
                    _has_python_function("recipes/experiment/cogsguard_marlbro.py", "train"),
                ),
                _keyword_check(
                    "coordination-style recipe wiring (keyword discovery)",
                    ("recipes/experiment",),
                    ("role_conditional", "_role_order"),
                ),
            ],
            support_type="trained" if coordination_shaper_exists else "backed",
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
                    "vibeservatory/backend/dashboard_backend/cogames_diagnose/router.py::get_doctor_note",
                    _has_python_function(
                        "vibeservatory/backend/dashboard_backend/cogames_diagnose/router.py", "get_doctor_note"
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
                    "vibeservatory/backend/dashboard_backend/state_page/diagnostics.py::compute_derived_metrics",
                    _has_python_function(
                        "vibeservatory/backend/dashboard_backend/state_page/diagnostics.py", "compute_derived_metrics"
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
                    "vibeservatory/backend/dashboard_backend/state_page/diagnostics.py::compute_instrumentation_validation",
                    _has_python_function(
                        "vibeservatory/backend/dashboard_backend/state_page/diagnostics.py",
                        "compute_instrumentation_validation",
                    ),
                ),
                (
                    "instrumentation summary included in dashboard response",
                    "vibeservatory/backend/dashboard_backend/state_page/router.py",
                    _contains_all(
                        "vibeservatory/backend/dashboard_backend/state_page/router.py",
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
                    "vibeservatory/backend/dashboard_backend/state_page/diagnostics.py::compute_episode_behavior_tags",
                    _has_python_function(
                        "vibeservatory/backend/dashboard_backend/state_page/diagnostics.py",
                        "compute_episode_behavior_tags",
                    ),
                ),
                (
                    "behavior tags attached to episodes",
                    "vibeservatory/backend/dashboard_backend/state_page/episode_builder.py",
                    _contains_all(
                        "vibeservatory/backend/dashboard_backend/state_page/episode_builder.py",
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
