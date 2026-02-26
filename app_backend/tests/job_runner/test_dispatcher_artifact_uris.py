import json
from unittest.mock import MagicMock
from uuid import uuid4

from metta.app_backend.job_runner import dispatcher
from metta.app_backend.job_runner.config import get_dispatch_config
from metta.app_backend.models.job_request import JobRequest, JobType


def _make_job_request() -> JobRequest:
    return JobRequest(
        id=uuid4(),
        job_type=JobType.episode,
        job={
            "type": "single_episode",
            "policy_uris": ["s3://ignored/policy.zip"],
            "assignments": [0],
            "env": {"name": "test-env"},
        },
        user_id="test-user",
    )


def test_create_episode_job_presigns_runner_artifacts(monkeypatch, mock_k8s_client):
    monkeypatch.setenv("POLICY_S3_BUCKET", "observatory-private")
    monkeypatch.setenv("EVAL_S3_BUCKET", "observatory-private")
    monkeypatch.delenv("AWS_ROLE_ARN", raising=False)
    monkeypatch.delenv("AWS_WEB_IDENTITY_TOKEN_FILE", raising=False)
    get_dispatch_config.cache_clear()

    s3_client = MagicMock()
    monkeypatch.setattr(dispatcher.boto3, "client", lambda *args, **kwargs: s3_client)
    monkeypatch.setattr(
        dispatcher,
        "presign_operation",
        lambda operation, bucket, key, expiration, presign_client: f"presigned://{operation}/{bucket}/{key}",
    )

    job = _make_job_request()
    dispatcher.create_episode_job(job, policy_s3_keys={0: "cogames/submissions/policy.zip"})

    body = mock_k8s_client.create_namespaced_job.call_args.kwargs["body"]
    env_vars = body.spec.template.spec.containers[0].env
    env_by_name = {env_var.name: env_var.value for env_var in env_vars}
    prefix = f"jobs/{job.id}"

    assert env_by_name["JOB_SPEC_URI"] == f"presigned://get/observatory-private/{prefix}/spec.json"
    assert env_by_name["RESULTS_URI"] == f"presigned://put/observatory-private/{prefix}/results.json"
    assert env_by_name["RUNTIME_INFO_URI"] == f"presigned://put/observatory-private/{prefix}/runtime_info.json"
    assert env_by_name["REPLAY_URI"] == f"presigned://put/observatory-private/{prefix}/replay.json.z"
    assert env_by_name["DEBUG_URI"] == f"presigned://put/observatory-private/{prefix}/debug.zip"
    assert json.loads(env_by_name["POLICY_LOG_URLS"]) == {
        "0": f"presigned://put/observatory-private/{prefix}/policy_agent_0.txt"
    }

    put_body = json.loads(s3_client.put_object.call_args.kwargs["Body"].decode("utf-8"))
    assert put_body["policy_uris"] == ["presigned://get/observatory-private/cogames/submissions/policy.zip"]


def test_build_presign_s3_client_uses_web_identity_for_current_role(monkeypatch, tmp_path):
    token_file = tmp_path / "token.jwt"
    token_file.write_text("test-web-identity-token", encoding="utf-8")

    monkeypatch.setenv("AWS_ROLE_ARN", "arn:aws:iam::123456789012:role/observatory-backend")
    monkeypatch.setenv("AWS_WEB_IDENTITY_TOKEN_FILE", str(token_file))
    get_dispatch_config.cache_clear()

    sts_client = MagicMock()
    sts_client.assume_role_with_web_identity.return_value = {
        "Credentials": {
            "AccessKeyId": "AKIA_WEB",
            "SecretAccessKey": "SECRET_WEB",
            "SessionToken": "TOKEN_WEB",
        }
    }
    presign_s3_client = MagicMock()

    def _fake_boto3_client(service_name: str, **kwargs):
        if service_name == "sts":
            return sts_client
        if service_name == "s3":
            if kwargs.get("aws_access_key_id") == "AKIA_WEB":
                return presign_s3_client
            return MagicMock()
        raise AssertionError(f"Unexpected service: {service_name}")

    monkeypatch.setattr(dispatcher.boto3, "client", _fake_boto3_client)

    client = dispatcher._build_presign_s3_client(expiration=4 * 60 * 60, endpoint="https://s3.test.local")
    assert client is presign_s3_client

    sts_client.assume_role_with_web_identity.assert_called_once_with(
        RoleArn="arn:aws:iam::123456789012:role/observatory-backend",
        RoleSessionName="job-artifact-presign",
        DurationSeconds=15300,
        WebIdentityToken="test-web-identity-token",
    )
