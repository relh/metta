from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from kubernetes.client.rest import ApiException

from metta.app_backend.job_runner.watcher import (
    _list_and_sync,
    _maybe_store_event,
    _watch_stream,
)

_WATCHER = "metta.app_backend.job_runner.watcher"


def _make_pod_dict(
    name: str = "test-pod",
    rv: str = "100",
    phase: str = "Running",
    node_name: str | None = "node-1",
) -> dict[str, Any]:
    return {
        "metadata": {
            "name": name,
            "resourceVersion": rv,
            "creationTimestamp": "2026-01-01T00:00:00Z",
        },
        "spec": {
            "nodeName": node_name,
            "containers": [{"name": "main", "image": "test:latest"}],
        },
        "status": {"phase": phase},
    }


def _pod_event(event_type: str, pod: dict[str, Any]) -> dict[str, Any]:
    return {"type": event_type, "raw_object": pod}


def _bookmark(rv: str) -> dict[str, Any]:
    return {"type": "BOOKMARK", "raw_object": {"metadata": {"resourceVersion": rv}}}


def _error(code: int = 0) -> dict[str, Any]:
    return {"type": "ERROR", "raw_object": {"code": code, "message": "err"}}


class TestMaybeStoreEvent:
    @patch(f"{_WATCHER}.store_k8s_event")
    def test_attaches_cached_node_labels(self, mock_store: MagicMock):
        pod = _make_pod_dict(phase="Running")
        cache: dict[str, dict[str, str]] = {"node-1": {"gpu": "a100"}}
        _maybe_store_event("eval", "ADDED", pod, cache, MagicMock())
        mock_store.assert_called_once_with("eval", "ADDED", pod, node_labels={"gpu": "a100"})

    @patch(f"{_WATCHER}.store_k8s_event")
    def test_fetches_node_labels_on_first_sighting(self, mock_store: MagicMock):
        pod = _make_pod_dict(phase="Succeeded")
        mock_core = MagicMock()
        mock_node = MagicMock()
        mock_node.metadata.labels = {"gpu": "h100"}
        mock_core.read_node.return_value = mock_node

        cache: dict[str, dict[str, str]] = {}
        _maybe_store_event("eval", "MODIFIED", pod, cache, mock_core)

        mock_core.read_node.assert_called_once_with("node-1")
        assert cache["node-1"] == {"gpu": "h100"}
        mock_store.assert_called_once_with("eval", "MODIFIED", pod, node_labels={"gpu": "h100"})

    @patch(f"{_WATCHER}.store_k8s_event")
    def test_caches_empty_on_node_fetch_failure(self, mock_store: MagicMock):
        pod = _make_pod_dict(phase="Failed")
        mock_core = MagicMock()
        mock_core.read_node.side_effect = Exception("refused")

        cache: dict[str, dict[str, str]] = {}
        _maybe_store_event("eval", "MODIFIED", pod, cache, mock_core)
        assert cache["node-1"] == {}

    @patch(f"{_WATCHER}.store_k8s_event")
    def test_no_node_name(self, mock_store: MagicMock):
        pod = _make_pod_dict(node_name=None)
        _maybe_store_event("eval", "ADDED", pod, {}, MagicMock())
        mock_store.assert_called_once_with("eval", "ADDED", pod, node_labels=None)


@pytest.fixture()
def watch_mocks():
    with (
        patch(f"{_WATCHER}.watch.Watch") as mock_watch_cls,
        patch(f"{_WATCHER}.get_dispatch_config") as mock_cfg,
        patch(f"{_WATCHER}.update_heartbeat"),
        patch(f"{_WATCHER}.store_k8s_event") as mock_store,
    ):
        mock_cfg.return_value.JOB_NAMESPACE = "default"
        stream = mock_watch_cls.return_value.stream
        yield stream, mock_store


class TestWatchStream:
    def test_processes_add_modify_delete(self, watch_mocks):
        stream, mock_store = watch_mocks
        stream.return_value = [
            _pod_event("ADDED", _make_pod_dict(rv="10")),
            _pod_event("MODIFIED", _make_pod_dict(rv="11")),
            _pod_event("DELETED", _make_pod_dict(rv="12")),
        ]

        rv = _watch_stream(MagicMock(), "eval", "5", {})

        assert rv == "12"
        assert mock_store.call_count == 3

    def test_bookmark_updates_rv_without_storing(self, watch_mocks):
        stream, mock_store = watch_mocks
        stream.return_value = [_bookmark("99")]

        rv = _watch_stream(MagicMock(), "eval", "5", {})

        assert rv == "99"
        mock_store.assert_not_called()

    def test_error_410_raises(self, watch_mocks):
        stream, _ = watch_mocks
        stream.return_value = [_error(code=410)]

        with pytest.raises(ApiException) as exc_info:
            _watch_stream(MagicMock(), "eval", "5", {})
        assert exc_info.value.status == 410

    def test_non_410_error_skipped(self, watch_mocks):
        stream, mock_store = watch_mocks
        pod = _make_pod_dict(rv="20")
        stream.return_value = [_error(code=500), _pod_event("ADDED", pod)]

        rv = _watch_stream(MagicMock(), "eval", "5", {})

        assert rv == "20"
        assert mock_store.call_count == 1

    def test_empty_stream_returns_initial_rv(self, watch_mocks):
        stream, mock_store = watch_mocks
        stream.return_value = []

        rv = _watch_stream(MagicMock(), "eval", "42", {})

        assert rv == "42"
        mock_store.assert_not_called()

    def test_mixed_event_sequence(self, watch_mocks):
        stream, mock_store = watch_mocks
        stream.return_value = [
            _pod_event("ADDED", _make_pod_dict(rv="10")),
            _bookmark("15"),
            _error(code=500),
            _pod_event("MODIFIED", _make_pod_dict(rv="20")),
            _bookmark("25"),
        ]

        rv = _watch_stream(MagicMock(), "eval", "5", {})

        assert rv == "25"
        assert mock_store.call_count == 2


class TestListAndSync:
    @patch(f"{_WATCHER}.store_k8s_event")
    @patch(f"{_WATCHER}._pod_to_dict")
    @patch(f"{_WATCHER}.get_dispatch_config")
    def test_syncs_pods_and_returns_rv(self, mock_cfg: MagicMock, mock_to_dict: MagicMock, mock_store: MagicMock):
        mock_cfg.return_value.JOB_NAMESPACE = "default"
        mock_to_dict.return_value = _make_pod_dict()

        mock_core = MagicMock()
        mock_pod_list = MagicMock()
        mock_pod_list.metadata.resource_version = "500"
        mock_pod_list.items = [MagicMock(), MagicMock()]
        mock_core.list_namespaced_pod.return_value = mock_pod_list

        rv = _list_and_sync(mock_core, "eval", {})

        assert rv == "500"
        assert mock_store.call_count == 2

    @patch(f"{_WATCHER}.store_k8s_event")
    @patch(f"{_WATCHER}.get_dispatch_config")
    def test_returns_none_on_missing_metadata(self, mock_cfg: MagicMock, mock_store: MagicMock):
        mock_cfg.return_value.JOB_NAMESPACE = "default"
        mock_core = MagicMock()
        mock_pod_list = MagicMock()
        mock_pod_list.metadata = None
        mock_core.list_namespaced_pod.return_value = mock_pod_list

        rv = _list_and_sync(mock_core, "eval", {})

        assert rv is None
        mock_store.assert_not_called()
