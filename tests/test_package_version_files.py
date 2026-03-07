import pytest

from metta.common.util.fs import get_repo_root

SYNCED_FILES: list[tuple[str, str]] = [
    (".nim-version", "cogames-agents/src/cogames_agents/policy/nim_agents/.nim-version"),
    (".nimby-version", "cogames-agents/src/cogames_agents/policy/nim_agents/.nimby-version"),
    (".nim-version", "packages/mettagrid/.nim-version"),
    (".nimby-version", "packages/mettagrid/.nimby-version"),
]


@pytest.mark.parametrize("root_file,package_file", SYNCED_FILES, ids=[p for _, p in SYNCED_FILES])
def test_package_version_file_matches_root(root_file: str, package_file: str) -> None:
    repo_root = get_repo_root()
    root_content = (repo_root / root_file).read_text().strip()
    pkg_content = (repo_root / package_file).read_text().strip()
    assert root_content == pkg_content, (
        f"{package_file} ({pkg_content}) does not match {root_file} ({root_content}). "
        f"Run: cp {root_file} {package_file}"
    )
