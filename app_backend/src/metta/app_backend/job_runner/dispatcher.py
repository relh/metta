import json
import logging
from typing import Literal

import boto3
from botocore.config import Config as BotoConfig
from kubernetes import client
from kubernetes.config.kube_config import load_kube_config

from metta.app_backend.job_runner.config import (
    LABEL_APP,
    LABEL_APP_VALUE,
    LABEL_JOB_ID,
    get_dispatch_config,
)
from metta.app_backend.job_runner.job_artifacts import (
    job_replay_key,
    job_results_key,
    job_runtime_info_key,
    job_spec_key,
)
from metta.app_backend.job_runner.tournament_cluster import get_tournament_client
from metta.app_backend.models.job_request import JobRequest, JobType
from metta.app_backend.tournament.settings import JOB_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


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
    original_policy_uris: list[str] = job_spec.pop("policy_uris", [])

    resolved_s3_keys: list[str] = []
    for i, uri in enumerate(original_policy_uris):
        key = (policy_s3_keys or {}).get(i)
        if key is None:
            raise ValueError(f"Missing pre-resolved S3 key for policy URI at index {i}: {uri}")
        resolved_s3_keys.append(key)

    exp = cfg.PRESIGNED_URL_EXPIRATION
    endpoint = cfg.S3_PRESIGNED_ENDPOINT
    job_spec["policy_uris"] = [
        presign_operation("get", cfg.POLICY_S3_BUCKET, k, exp, endpoint) for k in resolved_s3_keys
    ]

    s3_client = boto3.client("s3")
    spec_key = job_spec_key(job.id)
    s3_client.put_object(
        Bucket=cfg.EVAL_S3_BUCKET,
        Key=spec_key,
        Body=json.dumps(job_spec).encode("utf-8"),
        ContentType="application/json",
    )
    spec_uri = presign_operation("get", cfg.EVAL_S3_BUCKET, spec_key, exp, endpoint)
    results_uri = presign_operation("put", cfg.EVAL_S3_BUCKET, job_results_key(job.id), exp, endpoint)
    runtime_info_uri = presign_operation("put", cfg.EVAL_S3_BUCKET, job_runtime_info_key(job.id), exp, endpoint)
    env_vars: list[client.V1EnvVar] = [
        client.V1EnvVar(name="JOB_SPEC_URI", value=spec_uri),
        client.V1EnvVar(name="RESULTS_URI", value=results_uri),
        client.V1EnvVar(name="RUNTIME_INFO_URI", value=runtime_info_uri),
    ]
    if job.job.get("replay_uri") is not None:
        replay_uri = presign_operation("put", cfg.EVAL_S3_BUCKET, job_replay_key(job.id), exp, endpoint)
        env_vars.append(client.V1EnvVar(name="REPLAY_URI", value=replay_uri))

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

    affinity = (
        client.V1Affinity(
            node_affinity=client.V1NodeAffinity(
                preferred_during_scheduling_ignored_during_execution=[
                    client.V1PreferredSchedulingTerm(
                        weight=100,
                        preference=client.V1NodeSelectorTerm(
                            match_expressions=[
                                client.V1NodeSelectorRequirement(
                                    key="node.kubernetes.io/instance-type",
                                    operator="In",
                                    values=[
                                        "c5.xlarge",
                                        "c5.2xlarge",
                                        "c6i.xlarge",
                                        "c6i.2xlarge",
                                        "c7i.xlarge",
                                        "c7i.2xlarge",
                                    ],
                                )
                            ]
                        ),
                    )
                ]
            )
        )
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
                    affinity=affinity,
                    containers=[
                        client.V1Container(
                            name="worker",
                            image=cfg.EPISODE_RUNNER_IMAGE,
                            image_pull_policy="IfNotPresent" if cfg.LOCAL_DEV else "Always",
                            security_context=client.V1SecurityContext(
                                capabilities=client.V1Capabilities(add=["PERFMON"]),
                            ),
                            command=[
                                "uv",
                                "run",
                                "--no-sync",
                                "python",
                                "-m",
                                "metta.app_backend.job_runner.executor",
                            ],
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
    operation: Literal["get", "put"], bucket: str, key: str, expiration: int, endpoint: str | None
) -> str:
    s3_client = boto3.client(
        "s3",
        config=BotoConfig(signature_version="s3v4"),
        **({"endpoint_url": endpoint} if endpoint else {}),
    )
    return s3_client.generate_presigned_url(
        f"{operation}_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expiration,
    )
