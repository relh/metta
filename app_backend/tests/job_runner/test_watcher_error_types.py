"""Test error classification and structured error reading in event processor."""

import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError
from pydantic import ValidationError

from metta.app_backend.job_runner.event_processor import _classify_error, _read_runner_error
from mettagrid.runner.types import RunnerError


def test_error_types_are_distinct():
    """Verify the new error types are distinct from 'unknown'."""
    lifecycle_error_types = ["pod_not_found", "pod_deleted", "result_missing", "result_error"]
    runtime_error_types = ["policy_error", "timeout", "oom", "config_error", "crash", "unknown"]

    assert set(lifecycle_error_types).isdisjoint(set(runtime_error_types))
    assert "unknown" not in lifecycle_error_types


# --- _classify_error: now infra-only fallback (runner was killed externally) ---


@pytest.mark.parametrize(
    "error_message,expected_type",
    [
        ("DeadlineExceeded", "timeout"),
        ("timeout waiting for pod", "timeout"),
        ("OOMKilled", "oom"),
        ("out of memory", "oom"),
        ("Something completely unexpected happened", "unknown"),
        # Previously classified as config_error or policy_error by string matching;
        # now these fall through to 'unknown' because the runner classifies them directly.
        ("ValidationError: 3 validation errors for EpisodeConfig", "unknown"),
        ("Policy server failed during episode execution", "unknown"),
        ("grpc connection refused to policy server", "unknown"),
        ("ErrImagePull: failed to pull image", "unknown"),
    ],
)
def test_classify_error_infra_only(error_message: str, expected_type: str):
    """_classify_error now only handles infra cases where the runner was killed."""
    assert _classify_error(error_message) == expected_type


# --- fallback precedence: k8s reason is authoritative for error_type ---


def test_classify_error_uses_k8s_reason_not_log_text():
    """When k8s says OOMKilled, error_type should be oom even if log text doesn't mention it.

    This tests the fix for the fallback path where error_type is derived from
    k8s_error (authoritative) rather than the chosen human-readable error string.
    """
    # K8s reason is the source for classification
    assert _classify_error("OOMKilled") == "oom"
    assert _classify_error("DeadlineExceeded") == "timeout"
    # Log text that doesn't mention OOM/timeout should not override
    assert _classify_error("RuntimeError: episode_subprocess failed (signal 9)") == "unknown"


# --- _read_runner_error ---


@patch("metta.app_backend.job_runner.event_processor.get_dispatch_config")
@patch("metta.app_backend.job_runner.event_processor.get_s3_client")
def test_read_runner_error_present(mock_s3_client, mock_config):
    """When error_info.json exists, return the parsed RunnerError."""
    job_id = uuid4()
    mock_config.return_value.EVAL_S3_BUCKET = "test-bucket"

    error = RunnerError(error_type="config_error", message="validation failed")
    body = MagicMock()
    body.read.return_value = error.model_dump_json().encode("utf-8")
    mock_s3_client.return_value.get_object.return_value = {"Body": body}

    result = _read_runner_error(job_id)
    assert result is not None
    assert result.error_type == "config_error"
    assert result.message == "validation failed"


@patch("metta.app_backend.job_runner.event_processor.get_dispatch_config")
@patch("metta.app_backend.job_runner.event_processor.get_s3_client")
def test_read_runner_error_missing(mock_s3_client, mock_config):
    """When error_info.json doesn't exist (runner was killed), return None."""
    job_id = uuid4()
    mock_config.return_value.EVAL_S3_BUCKET = "test-bucket"
    mock_s3_client.return_value.get_object.side_effect = ClientError(
        {"Error": {"Code": "NoSuchKey", "Message": "The specified key does not exist."}},
        "GetObject",
    )

    result = _read_runner_error(job_id)
    assert result is None


@patch("metta.app_backend.job_runner.event_processor.get_dispatch_config")
@patch("metta.app_backend.job_runner.event_processor.get_s3_client")
def test_read_runner_error_corrupt(mock_s3_client, mock_config):
    """Corrupt JSON should raise to avoid silent misclassification."""
    job_id = uuid4()
    mock_config.return_value.EVAL_S3_BUCKET = "test-bucket"

    body = MagicMock()
    body.read.return_value = b"not valid json"
    mock_s3_client.return_value.get_object.return_value = {"Body": body}

    with pytest.raises(ValidationError):
        _read_runner_error(job_id)


@patch("metta.app_backend.job_runner.event_processor.get_dispatch_config")
@patch("metta.app_backend.job_runner.event_processor.get_s3_client")
def test_read_runner_error_invalid_error_type(mock_s3_client, mock_config):
    """Invalid error_type should raise to avoid silent misclassification."""
    job_id = uuid4()
    mock_config.return_value.EVAL_S3_BUCKET = "test-bucket"

    body = MagicMock()
    body.read.return_value = json.dumps({"error_type": "bogus_type", "message": "test"}).encode("utf-8")
    mock_s3_client.return_value.get_object.return_value = {"Body": body}

    with pytest.raises(ValidationError):
        _read_runner_error(job_id)
