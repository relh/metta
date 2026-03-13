import pytest

from metta.common.compat_version import get_compat_version
from metta.common.training_compat import (
    format_training_compat_metric_label,
    get_training_compat_record,
    get_training_compat_target,
    get_training_compat_version,
    list_training_compat_versions,
)


def test_get_training_compat_version_returns_str() -> None:
    assert isinstance(get_training_compat_version(), str)


def test_current_training_compat_record_tracks_current_env_compat() -> None:
    record = get_training_compat_record()
    assert record.version == get_training_compat_version()
    assert record.env_compat_version == get_compat_version()
    assert len(record.targets) >= 2


def test_get_training_compat_target_for_arena_stable_jobs() -> None:
    single_gpu = get_training_compat_target("arena_basic_easy_shaped.train_100m")
    multi_gpu = get_training_compat_target("arena_basic_easy_shaped.train_2b")

    assert single_gpu.metric == "overview/sps"
    assert single_gpu.expected_min == 15_000
    assert single_gpu.tool_path == "recipes.prod.arena_basic_easy_shaped.train_100m"

    assert multi_gpu.metric == "overview/sps"
    assert multi_gpu.expected_min == 52_000
    assert multi_gpu.tool_path == "recipes.prod.arena_basic_easy_shaped.train_2b"


def test_format_training_compat_metric_label_includes_anchor_context() -> None:
    label = format_training_compat_metric_label("arena_basic_easy_shaped.train_100m")
    assert "training compat 1.0" in label
    assert "commit 6c8f7369e6b6" in label
    assert "env compat 0.19" in label
    assert "expected >=" in label


def test_unknown_training_compat_target_raises_clear_error() -> None:
    with pytest.raises(ValueError, match="Unknown training compat target"):
        get_training_compat_target("arena_basic_easy_shaped.unknown")


def test_training_compat_versions_include_current_file_value() -> None:
    assert get_training_compat_version() in list_training_compat_versions()
