import json
import logging
import os
from pathlib import Path
from typing import Any, Literal

import boto3
from botocore import UNSIGNED
from botocore.config import Config as BotoConfig
from kubernetes import client
from kubernetes.config.kube_config import load_kube_config

from metta.app_backend.job_runner.config import (
    LABEL_APP,
    LABEL_APP_VALUE,
    LABEL_JOB_ID,
    get_dispatch_config,
)
from metta.app_backend.job_runner.job_artifacts import JobArtifact, job_policy_log_key
from metta.app_backend.job_runner.tournament_cluster import get_tournament_client
from metta.app_backend.models.job_request import JobRequest, JobType
from metta.app_backend.tournament.settings import JOB_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

_MAX_ASSUME_ROLE_DURATION_SECONDS = 12 * 60 * 60
_PRESIGN_ROLE_SESSION_NAME = "job-artifact-presign"
_PRESIGN_ROLE_DURATION_BUFFER_SECONDS = 900


def _assume_role_with_web_identity(
    role_arn: str,
    role_session_name: str,
    duration_seconds: int,
    web_identity_token_file: str,
) -> dict[str, str]:
    token = Path(web_identity_token_file).read_text(encoding="utf-8").strip()
    assumed = boto3.client("sts", config=BotoConfig(signature_version=UNSIGNED)).assume_role_with_web_identity(
        RoleArn=role_arn,
        RoleSessionName=role_session_name,
        DurationSeconds=duration_seconds,
        WebIdentityToken=token,
    )
    creds = assumed["Credentials"]
    return {
        "aws_access_key_id": creds["AccessKeyId"],
        "aws_secret_access_key": creds["SecretAccessKey"],
        "aws_session_token": creds["SessionToken"],
    }


def _build_presign_s3_client(expiration: int, endpoint: str | None) -> Any:
    client_kwargs = {
        "config": BotoConfig(signature_version="s3v4"),
        **({"endpoint_url": endpoint} if endpoint else {}),
    }
    requested_duration = expiration + _PRESIGN_ROLE_DURATION_BUFFER_SECONDS
    duration = min(_MAX_ASSUME_ROLE_DURATION_SECONDS, max(900, requested_duration))
    presign_role_arn = os.environ.get("AWS_ROLE_ARN")
    web_identity_token_file = os.environ.get("AWS_WEB_IDENTITY_TOKEN_FILE")

    if presign_role_arn and web_identity_token_file:
        web_identity_creds = _assume_role_with_web_identity(
            role_arn=presign_role_arn,
            role_session_name=_PRESIGN_ROLE_SESSION_NAME,
            duration_seconds=duration,
            web_identity_token_file=web_identity_token_file,
        )
        return boto3.client("s3", **web_identity_creds, **client_kwargs)

    return boto3.client("s3", **client_kwargs)


def get_k8s_client() -> client.BatchV1Api:
    cfg = get_dispatch_config()
    if cfg.LOCAL_DEV:
        if not cfg.LOCAL_DEV_K8S_CONTEXT:
            raise ValueError("LOCAL_DEV=true requires LOCAL_DEV_K8S_CONTEXT to be set")
        load_kube_config(context=cfg.LOCAL_DEV_K8S_CONTEXT)
        return client.BatchV1Api()
    return get_tournament_client()


def dispatch_job(job: JobRequest, policy_s3_keys: dict[int, str] | None = None) -> str:
    if job.job_type == JobType.episode:
        return create_episode_job(job, policy_s3_keys or {})
    raise ValueError(f"Unknown job type: {job.job_type}")


def create_episode_job(job: JobRequest, policy_s3_keys: dict[int, str] | None = None) -> str:
    cfg = get_dispatch_config()
    batch_v1 = get_k8s_client()
    job_name = f"job-{job.id.hex[:8]}"

    if not cfg.POLICY_S3_BUCKET or not cfg.EVAL_S3_BUCKET:
        raise ValueError("POLICY_S3_BUCKET and EVAL_S3_BUCKET must be set")
    job_spec = job.job.copy()
    episode_runner_image = job_spec.pop("episode_runner_image", None) or cfg.EPISODE_RUNNER_IMAGE
    original_policy_uris: list[str] = job_spec.pop("policy_uris", [])

    resolved_s3_keys: list[str] = []
    for i, uri in enumerate(original_policy_uris):
        key = (policy_s3_keys or {}).get(i)
        if key is None:
            raise ValueError(f"Missing pre-resolved S3 key for policy URI at index {i}: {uri}")
        resolved_s3_keys.append(key)

    exp = JOB_TIMEOUT_SECONDS + 3600
    endpoint = cfg.S3_PRESIGNED_ENDPOINT
    presign_s3_client = _build_presign_s3_client(exp, endpoint)
    job_spec["policy_uris"] = [
        presign_operation("get", cfg.POLICY_S3_BUCKET, k, exp, presign_s3_client) for k in resolved_s3_keys
    ]
    s3_client = boto3.client("s3")
    spec_key = JobArtifact.SPEC.key(job.id)
    s3_client.put_object(
        Bucket=cfg.EVAL_S3_BUCKET,
        Key=spec_key,
        Body=json.dumps(job_spec).encode("utf-8"),
        ContentType="application/json",
    )
    env_vars: list[client.V1EnvVar] = [
        client.V1EnvVar(
            name=artifact.env_var,
            value=presign_operation(
                artifact.direction,
                cfg.EVAL_S3_BUCKET,
                artifact.key(job.id),
                exp,
                presign_s3_client,
            ),
        )
        for artifact in JobArtifact.presigned()
        if artifact.env_var is not None
    ]

    # Generate presigned URLs for per-agent policy logs
    assignments: list[int] = job_spec.get("assignments", [])
    policy_log_urls: dict[str, str] = {}
    for agent_idx in range(len(assignments)):
        key = job_policy_log_key(job.id, agent_idx)
        url = presign_operation("put", cfg.EVAL_S3_BUCKET, key, exp, presign_s3_client)
        policy_log_urls[str(agent_idx)] = url
    if policy_log_urls:
        env_vars.append(
            client.V1EnvVar(
                name="POLICY_LOG_URLS",
                value=json.dumps(policy_log_urls),
            )
        )

    if cfg.LOCAL_DEV and cfg.LOCAL_DEV_AWS_PROFILE:
        env_vars.append(client.V1EnvVar(name="AWS_PROFILE", value=cfg.LOCAL_DEV_AWS_PROFILE))

    labels = {
        LABEL_APP: LABEL_APP_VALUE,
        LABEL_JOB_ID: str(job.id),
    }

    volumes: list[client.V1Volume] = []
    volume_mounts: list[client.V1VolumeMount] = []

    if cfg.LOCAL_DEV and cfg.LOCAL_DEV_MOUNTS:
        for i, mount in enumerate(cfg.LOCAL_DEV_MOUNTS.split(",")):
            parts = mount.strip().split(":")
            if len(parts) != 2:
                logger.warning(f"Invalid mount format: {mount}, expected 'host:container'")
                continue
            host_path, container_path = parts
            vol_name = f"local-mount-{i}"
            volumes.append(
                client.V1Volume(
                    name=vol_name,
                    host_path=client.V1HostPathVolumeSource(path=host_path),
                )
            )
            volume_mounts.append(client.V1VolumeMount(name=vol_name, mount_path=container_path))

    tolerations: list[client.V1Toleration] | None = (
        [
            client.V1Toleration(
                key="workload-type",
                operator="Equal",
                value="jobs",
                effect="NoSchedule",
            )
        ]
        if not cfg.LOCAL_DEV
        else None
    )

    node_selector = (
        {
            "workload-type": "jobs",
        }
        if not cfg.LOCAL_DEV
        else None
    )

    k8s_job = client.V1Job(
        metadata=client.V1ObjectMeta(
            name=job_name,
            namespace=cfg.JOB_NAMESPACE,
            labels=labels,
        ),
        spec=client.V1JobSpec(
            backoff_limit=0,
            active_deadline_seconds=JOB_TIMEOUT_SECONDS,
            ttl_seconds_after_finished=3600,
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(
                    labels=labels,
                    annotations={
                        "karpenter.sh/do-not-disrupt": "true",
                    },
                ),
                spec=client.V1PodSpec(
                    restart_policy="Never",
                    service_account_name="episode-runner" if not cfg.LOCAL_DEV else None,
                    volumes=volumes,
                    tolerations=tolerations,
                    node_selector=node_selector,
                    containers=[
                        client.V1Container(
                            name="worker",
                            image=episode_runner_image,
                            image_pull_policy="IfNotPresent" if cfg.LOCAL_DEV else "Always",
                            security_context=client.V1SecurityContext(
                                capabilities=client.V1Capabilities(add=["PERFMON"]),
                            ),
                            env=env_vars,
                            volume_mounts=volume_mounts,
                            resources=client.V1ResourceRequirements(
                                requests={"cpu": "3", "memory": ("8Gi" if cfg.LOCAL_DEV else "16Gi")},
                                limits={"cpu": "4", "memory": ("12Gi" if cfg.LOCAL_DEV else "24Gi")},
                            ),
                        )
                    ],
                ),
            ),
        ),
    )

    batch_v1.create_namespaced_job(namespace=cfg.JOB_NAMESPACE, body=k8s_job)
    logger.info(f"Created k8s Job {job_name} for job {job.id}")
    return job_name


def presign_operation(
    operation: Literal["get", "put"],
    bucket: str,
    key: str,
    expiration: int,
    s3_client: Any,
) -> str:
    return s3_client.generate_presigned_url(
        f"{operation}_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expiration,
    )
