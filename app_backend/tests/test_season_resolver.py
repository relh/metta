from metta.app_backend.tournament.season_resolver import parse_season_ref


def test_parse_season_ref_simple_name():
    name, version = parse_season_ref("beta-cogsguard")
    assert name == "beta-cogsguard"
    assert version is None


def test_parse_season_ref_with_version():
    name, version = parse_season_ref("beta-cogsguard:v2")
    assert name == "beta-cogsguard"
    assert version == 2


def test_parse_season_ref_with_version_no_v():
    name, version = parse_season_ref("beta-cogsguard:3")
    assert name == "beta-cogsguard"
    assert version == 3


def test_parse_season_ref_with_invalid_version():
    name, version = parse_season_ref("beta-cogsguard:invalid")
    assert name == "beta-cogsguard:invalid"
    assert version is None


def test_parse_season_ref_with_invalid_v_version():
    name, version = parse_season_ref("beta-cogsguard:vX")
    assert name == "beta-cogsguard:vX"
    assert version is None


def test_parse_season_ref_with_empty_v_version():
    name, version = parse_season_ref("beta-cogsguard:v")
    assert name == "beta-cogsguard:v"
    assert version is None
