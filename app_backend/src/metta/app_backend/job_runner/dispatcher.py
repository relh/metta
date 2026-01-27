import functools
import logging
from dataclasses import dataclass
from urllib.parse import urlparse
from uuid import UUID

import boto3
from kubernetes import client
from kubernetes.config.incluster_config import load_incluster_config
from kubernetes.config.kube_config import load_kube_config

from metta.app_backend.clients.stats_client import StatsClient
from metta.app_backend.job_runner.config import (
    LABEL_APP,
    LABEL_APP_VALUE,
    LABEL_JOB_ID,
    get_dispatch_config,
)
from metta.app_backend.metta_scheme_resolver import MettaSchemeResolver
from metta.app_backend.models.job_request import JobRequest, JobType

logger = logging.getLogger(__name__)


def resolve_policy_uri_to_s3_key(uri: str, stats_client: StatsClient) -> str:
    if uri.startswith("metta://"):
        resolver = MettaSchemeResolver(stats_client=stats_client)
        return resolver.get_s3_key(uri)

    if uri.startswith("s3://"):
        parsed = urlparse(uri)
        return parsed.path.lstrip("/")

    raise ValueError(f"Unsupported policy URI scheme: {uri}")


@functools.cache
def get_k8s_client() -> client.BatchV1Api:
    cfg = get_dispatch_config()

    if cfg.LOCAL_DEV:
        if not cfg.LOCAL_DEV_K8S_CONTEXT:
            raise ValueError("LOCAL_DEV=true requires LOCAL_DEV_K8S_CONTEXT to be set")
        load_kube_config(context=cfg.LOCAL_DEV_K8S_CONTEXT)
    else:
        load_incluster_config()

    return client.BatchV1Api()


def dispatch_job(job: JobRequest) -> str:
    if job.job_type == JobType.episode:
        return create_episode_job(job)
    raise ValueError(f"Unknown job type: {job.job_type}")


def create_episode_job(job: JobRequest) -> str:
    cfg = get_dispatch_config()
    batch_v1 = get_k8s_client()
    job_name = f"job-{job.id.hex[:8]}"

    env_vars: list[client.V1EnvVar] = []

    if cfg.EVAL_S3_BUCKET:
        job_spec = job.job
        original_policy_uris: list[str] = job_spec.get("policy_uris", [])

        stats_client = StatsClient.create(cfg.STATS_SERVER_URI)
        policy_s3_keys = [resolve_policy_uri_to_s3_key(uri, stats_client) for uri in original_policy_uris]

        urls = generate_job_presigned_urls(
            job_id=job.id,
            policy_s3_keys=policy_s3_keys,
            eval_bucket=cfg.EVAL_S3_BUCKET,
            policy_bucket=cfg.POLICY_S3_BUCKET,
            expiration=cfg.PRESIGNED_URL_EXPIRATION,
        )

        import requests

        spec_to_write = {**job_spec, "policy_uris": urls.policy_uris}
        response = requests.put(
            urls.spec_put_uri,
            json=spec_to_write,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()

        env_vars = [
            client.V1EnvVar(name="JOB_SPEC_URI", value=urls.spec_get_uri),
            client.V1EnvVar(name="RESULTS_URI", value=urls.results_uri),
            client.V1EnvVar(name="REPLAY_URI", value=urls.replay_uri),
        ]
    else:
        env_vars = [
            client.V1EnvVar(name="STATS_SERVER_URI", value=cfg.STATS_SERVER_URI),
            client.V1EnvVar(name="MACHINE_TOKEN", value=cfg.MACHINE_TOKEN),
        ]

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
            active_deadline_seconds=3600,
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
                                "metta.sim.single_episode_runner",
                                str(job.id),
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


@dataclass
class JobPresignedUrls:
    spec_put_uri: str
    spec_get_uri: str
    results_uri: str
    replay_uri: str
    policy_uris: list[str]


def generate_job_presigned_urls(
    job_id: UUID,
    policy_s3_keys: list[str],
    eval_bucket: str,
    policy_bucket: str,
    expiration: int = 3600,
) -> JobPresignedUrls:
    s3_client = boto3.client("s3")
    job_prefix = f"jobs/{job_id}"

    spec_put_uri = s3_client.generate_presigned_url(
        "put_object",
        Params={"Bucket": eval_bucket, "Key": f"{job_prefix}/spec.json", "ContentType": "application/json"},
        ExpiresIn=expiration,
    )
    spec_get_uri = s3_client.generate_presigned_url(
        "get_object",
        Params={"Bucket": eval_bucket, "Key": f"{job_prefix}/spec.json"},
        ExpiresIn=expiration,
    )

    results_uri = s3_client.generate_presigned_url(
        "put_object",
        Params={"Bucket": eval_bucket, "Key": f"{job_prefix}/results.json", "ContentType": "application/json"},
        ExpiresIn=expiration,
    )

    replay_uri = s3_client.generate_presigned_url(
        "put_object",
        Params={"Bucket": eval_bucket, "Key": f"{job_prefix}/replay.json.z", "ContentType": "application/x-compress"},
        ExpiresIn=expiration,
    )

    policy_uris = [
        s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": policy_bucket, "Key": key},
            ExpiresIn=expiration,
        )
        for key in policy_s3_keys
    ]

    return JobPresignedUrls(
        spec_put_uri=spec_put_uri,
        spec_get_uri=spec_get_uri,
        results_uri=results_uri,
        replay_uri=replay_uri,
        policy_uris=policy_uris,
    )
