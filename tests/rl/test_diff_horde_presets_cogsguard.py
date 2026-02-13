import pytest

from metta.rl.diff_horde.presets.cogsguard import (
    AVAILABLE_HORDE_VARIANTS,
    normalize_horde_variant_names,
    resolve_cogsguard_horde_cumulants,
)


def test_normalize_horde_variant_names_parses_json_list_string() -> None:
    names = normalize_horde_variant_names('["junctions","vitals"]')
    assert names == ["junctions", "vitals"]


def test_resolve_cogsguard_horde_cumulants_returns_none_when_empty() -> None:
    assert resolve_cogsguard_horde_cumulants(None) is None
    assert resolve_cogsguard_horde_cumulants([]) is None


def test_resolve_cogsguard_horde_cumulants_builds_junction_specs() -> None:
    cfg = resolve_cogsguard_horde_cumulants(["junctions"])
    assert cfg is not None

    specs_by_name = {spec.name: spec for spec in cfg.specs}
    assert set(specs_by_name) == {"cogs_junction_now", "clips_junction_now"}
    assert specs_by_name["cogs_junction_now"].key == "env_collective/cogs/aligned.junction"
    assert specs_by_name["clips_junction_now"].key == "env_collective/clips/aligned.junction"


def test_resolve_cogsguard_horde_cumulants_deduplicates_variant_names() -> None:
    cfg = resolve_cogsguard_horde_cumulants(["junctions", "junctions", "vitals"])
    assert cfg is not None
    assert cfg.num_cumulants == 6


def test_resolve_cogsguard_horde_cumulants_raises_on_unknown_variant() -> None:
    with pytest.raises(ValueError, match="Unknown CogsGuard horde variant"):
        resolve_cogsguard_horde_cumulants(["unknown"])
    assert "junctions" in AVAILABLE_HORDE_VARIANTS


def test_resolve_cogsguard_horde_cumulants_supports_cortex_core_td_key() -> None:
    cfg = resolve_cogsguard_horde_cumulants(["cortex_core"])
    assert cfg is not None

    assert [spec.name for spec in cfg.specs] == ["cortex_core"]
    assert cfg.specs[0].kind == "td_key"
    assert cfg.specs[0].key == "core"


def test_resolve_cogsguard_horde_cumulants_all_alias_includes_all_concrete_variants() -> None:
    cfg_all = resolve_cogsguard_horde_cumulants(["all"])
    cfg_explicit = resolve_cogsguard_horde_cumulants(
        [
            "junctions",
            "vitals",
            "roles",
            "cortex_core",
            "economy_agent",
            "economy_collective",
            "tempo",
            "junction_events",
            "economy_flow",
            "action_counters",
        ]
    )
    assert cfg_all is not None
    assert cfg_explicit is not None
    assert [spec.model_dump(exclude_none=True) for spec in cfg_all.specs] == [
        spec.model_dump(exclude_none=True) for spec in cfg_explicit.specs
    ]
