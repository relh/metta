from __future__ import annotations

import base64
import logging
import os
import tempfile
import time
from typing import Any

import boto3
from botocore.signers import RequestSigner
from kubernetes import client
from kubernetes.client import ApiClient, Configuration  # type: ignore[attr-defined]

from metta.app_backend.job_runner.config import get_dispatch_config

logger = logging.getLogger(__name__)

_CREDS_TTL_SECONDS = 2700  # 45 min (assumed role creds last 1 hour)

_assumed_creds: dict[str, str] | None = None
_creds_at: float = 0
_sts_client: Any = None
_cluster_endpoint: str | None = None
_ca_path: str | None = None
_config: Configuration | None = None
_batch_api: client.BatchV1Api | None = None


# Generates an EKS-compatible bearer token by creating a presigned STS GetCallerIdentity URL.
# boto3 has no SDK equivalent of `aws eks get-token`; this presigned-URL approach is the
# standard workaround for Python. The EKS API server decodes the token, calls the presigned
# URL to verify the caller's IAM identity, and maps it to a k8s identity via access entries.
# See: https://docs.aws.amazon.com/eks/latest/userguide/cluster-auth.html
def _get_eks_bearer_token(sts_client: Any, cluster_name: str) -> str:
    signer = RequestSigner(
        sts_client.meta.service_model.service_id,
        sts_client.meta.region_name,
        "sts",
        "v4",
        sts_client._request_signer._credentials,
        sts_client.meta.events,
    )
    url = f"{sts_client.meta.endpoint_url}/?Action=GetCallerIdentity&Version=2011-06-15"
    signed_url = signer.generate_presigned_url(
        {"method": "GET", "url": url, "body": {}, "headers": {"x-k8s-aws-id": cluster_name}, "context": {}},
        region_name=sts_client.meta.region_name,
        expires_in=60,
        operation_name="",
    )
    if not signed_url:
        raise ValueError("Failed to get EKS bearer token")
    return "k8s-aws-v1." + base64.urlsafe_b64encode(signed_url.encode("utf-8")).rstrip(b"=").decode("utf-8")


def _refresh_creds() -> dict[str, str]:
    global _assumed_creds, _creds_at, _sts_client
    now = time.monotonic()
    if _assumed_creds is not None and now - _creds_at < _CREDS_TTL_SECONDS:
        return _assumed_creds

    cfg = get_dispatch_config()
    assumed = boto3.client("sts").assume_role(
        RoleArn=cfg.EVAL_CLUSTER_ROLE_ARN,
        RoleSessionName="dispatcher-eval-access",
        ExternalId=cfg.EVAL_CLUSTER_EXTERNAL_ID,
    )
    creds = assumed["Credentials"]
    _assumed_creds = dict(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
    )
    _creds_at = now
    _sts_client = boto3.client("sts", region_name=cfg.EVAL_CLUSTER_REGION, **_assumed_creds)
    logger.info("Refreshed tournament account assumed role credentials")
    return _assumed_creds


def _get_cluster_info(assumed_creds: dict[str, str]) -> tuple[str, str]:
    global _cluster_endpoint, _ca_path, _config, _batch_api
    if _cluster_endpoint is not None and _ca_path is not None and os.path.exists(_ca_path):
        return _cluster_endpoint, _ca_path
    _batch_api = None
    _config = None

    cfg = get_dispatch_config()
    eks = boto3.client("eks", region_name=cfg.EVAL_CLUSTER_REGION, **assumed_creds)
    cluster = eks.describe_cluster(name=cfg.EVAL_CLUSTER_NAME)["cluster"]

    ca_file = tempfile.NamedTemporaryFile(delete=False, suffix=".crt")
    ca_file.write(base64.b64decode(cluster["certificateAuthority"]["data"]))
    ca_file.close()

    endpoint: str = cluster["endpoint"]
    ca_path: str = ca_file.name
    _cluster_endpoint = endpoint
    _ca_path = ca_path

    logger.info(f"Cached tournament cluster info: endpoint={endpoint}")
    return endpoint, ca_path


def get_tournament_client() -> client.BatchV1Api:
    global _config, _batch_api

    cfg = get_dispatch_config()
    if not cfg.EVAL_CLUSTER_ROLE_ARN or not cfg.EVAL_CLUSTER_NAME:
        raise ValueError("EVAL_CLUSTER_ROLE_ARN and EVAL_CLUSTER_NAME must be set")

    assumed_creds = _refresh_creds()
    endpoint, ca_path = _get_cluster_info(assumed_creds)
    token = _get_eks_bearer_token(_sts_client, cfg.EVAL_CLUSTER_NAME)

    if _batch_api is None or _config is None:
        config = Configuration()
        config.host = endpoint
        config.ssl_ca_cert = ca_path  # type: ignore
        config.api_key = {"authorization": f"Bearer {token}"}
        _config = config
        _batch_api = client.BatchV1Api(ApiClient(config))
    else:
        _config.api_key = {"authorization": f"Bearer {token}"}

    return _batch_api
