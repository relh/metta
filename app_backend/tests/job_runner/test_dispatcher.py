from unittest.mock import MagicMock, patch
from uuid import uuid4

from metta.app_backend.job_runner.dispatcher import (
    generate_job_presigned_urls,
    resolve_policy_uri_to_s3_key,
)


def test_generate_job_presigned_urls():
    job_id = uuid4()
    policy_s3_keys = ["policies/v1.pt", "policies/v2.pt"]

    with patch("metta.app_backend.job_runner.dispatcher.boto3.client") as mock_boto:
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = "https://signed-url"
        mock_boto.return_value = mock_s3

        urls = generate_job_presigned_urls(
            job_id=job_id,
            policy_s3_keys=policy_s3_keys,
            eval_bucket="eval-bucket",
            policy_bucket="policy-bucket",
            expiration=3600,
        )

    assert urls.spec_put_uri == "https://signed-url"
    assert urls.spec_get_uri == "https://signed-url"
    assert urls.results_uri == "https://signed-url"
    assert urls.replay_uri == "https://signed-url"
    assert len(urls.policy_uris) == 2


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
