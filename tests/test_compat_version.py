from metta.common.compat_version import get_compat_version, parse_compat_version


def test_get_compat_version_returns_str() -> None:
    v = get_compat_version()
    assert isinstance(v, str)
    assert v == "0.4"


def test_parse_compat_version_3_part() -> None:
    assert parse_compat_version("0.4.2") == "0.4"


def test_parse_compat_version_1_0() -> None:
    assert parse_compat_version("1.0.3") == "1.0"


def test_parse_compat_version_4_part_old_format() -> None:
    assert parse_compat_version("0.2.0.98") == "0.2"


def test_parse_compat_version_dev() -> None:
    assert parse_compat_version("0.4.2.post1.dev375") == "0.4"


def test_parse_compat_version_invalid() -> None:
    assert parse_compat_version("not-a-version") is None
