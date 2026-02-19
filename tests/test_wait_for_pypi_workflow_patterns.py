from metta.common.util.fs import get_repo_root


def test_wait_for_pypi_workflows_use_delimited_version_match_regression() -> None:
    repo_root = get_repo_root()
    wait_workflow = (repo_root / ".github/workflows/_wait-for-pypi.yml").read_text()
    episode_runner_workflow = (repo_root / ".github/workflows/build-episode-runner-image.yml").read_text()
    release_workflow = (repo_root / ".github/workflows/release-cogames.yml").read_text()

    assert 'grep -qE "${DEPENDENCY}-${VERSION}(-|\\\\.|$)"' in wait_workflow
    assert 'grep -qE "cogames-${VERSION}(-|\\\\.|$)"' in episode_runner_workflow
    assert 'grep -qE "cogames-${VERSION}(-|\\\\.|$)"' in release_workflow
