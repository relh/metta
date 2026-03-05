from __future__ import annotations

import pytest

from metta.setup.tools.code_formatters import get_file_linters

pytestmark = pytest.mark.setup


def test_markdown_is_not_registered_as_a_file_linter() -> None:
    linter_names = {linter.name for linter in get_file_linters()}

    assert "Markdown" not in linter_names
