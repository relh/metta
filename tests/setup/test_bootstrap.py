import pytest

from metta.setup.components.system_packages.bootstrap import version_ge


@pytest.mark.setup
class TestVersionGe:
    @pytest.mark.parametrize(
        ("current", "required", "expected"),
        [
            ("1.2.3", "1.2.3", True),
            ("2.0.0", "1.9.9", True),
            ("1.3.0", "1.2.9", True),
            ("1.2.4", "1.2.3", True),
            ("1.0.0", "2.0.0", False),
            ("1.2.0", "1.3.0", False),
            ("1.2.2", "1.2.3", False),
            (None, "1.0.0", False),
            ("", "1.0.0", False),
            ("1.2.3.4", "1.2.3", True),
            ("1.2", "1.2.0", True),
            ("1.2", "1.2.1", False),
        ],
    )
    def test_core_comparisons(self, current, required, expected):
        assert version_ge(current, required) is expected

    @pytest.mark.parametrize(
        ("current", "required", "expected"),
        [
            ("2.2.6", "2.2.6", True),
            ("2.2.7", "2.2.6", True),
            ("2.2.5", "2.2.6", False),
            ("0.1.13", "0.1.13", True),
            ("0.1.14", "0.1.13", True),
            ("0.1.12", "0.1.13", False),
            ("7.0.0", "7.0.0", True),
            ("7.1.0", "7.0.0", True),
            ("6.5.0", "7.0.0", False),
        ],
    )
    def test_real_versions(self, current, required, expected):
        assert version_ge(current, required) is expected
