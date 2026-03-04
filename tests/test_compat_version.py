from typing import Optional

import pytest

from metta.common.compat_version import get_compat_version, parse_compat_version


def test_get_compat_version_returns_str() -> None:
    v = get_compat_version()
    assert isinstance(v, str)


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ("0.4.2", "0.4"),
        ("1.0.3", "1.0"),
        ("0.2.0.98", "0.2"),
        ("0.4.2.post1.dev375", "0.4"),
        ("not-a-version", None),
    ],
)
def test_parse_compat_version(version: str, expected: Optional[str]) -> None:
    assert parse_compat_version(version) == expected
