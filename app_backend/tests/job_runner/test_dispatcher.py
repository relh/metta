from unittest.mock import MagicMock
from uuid import uuid4

from metta.app_backend.job_runner.dispatcher import (
    resolve_policy_uri_to_s3_key,
)


def test_resolve_policy_uri_s3():
    mock_stats_client = MagicMock()
    key = resolve_policy_uri_to_s3_key("s3://my-bucket/policies/v1/checkpoint.pt", mock_stats_client)
    assert key == "policies/v1/checkpoint.pt"
    mock_stats_client.get_policy_version.assert_not_called()


def test_resolve_policy_uri_metta():
    policy_version_id = uuid4()
    mock_stats_client = MagicMock()
    mock_stats_client.get_policy_version.return_value.s3_path = "s3://bucket/policies/test.pt"

    key = resolve_policy_uri_to_s3_key(f"metta://policy/{policy_version_id}", mock_stats_client)

    assert key == "policies/test.pt"
    mock_stats_client.get_policy_version.assert_called_once_with(policy_version_id)
