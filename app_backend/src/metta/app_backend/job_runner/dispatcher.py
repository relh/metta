import base64
import functools
import json
import logging
import tempfile
from typing import Literal

import boto3
from botocore.signers import RequestSigner
from kubernetes import client
from kubernetes.client import ApiClient, Configuration
from kubernetes.config.incluster_config import load_incluster_config
from kubernetes.config.kube_config import load_kube_config

from metta.app_backend.job_runner.config import (
    LABEL_APP,
    LABEL_APP_VALUE,
    LABEL_JOB_ID,
    get_dispatch_config,
)
from metta.app_backend.models.job_request import JobRequest, JobType
from metta.app_backend.tournament.settings import JOB_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


# Generates an EKS-compatible bearer token by creating a presigned STS GetCallerIdentity URL.
# boto3 has no SDK equivalent of `aws eks get-token`; this presigned-URL approach is the
# standard workaround for Python. The EKS API server decodes the token, calls the presigned
# URL to verify the caller's IAM identity, and maps it to a k8s identity via access entries.
# See: https://docs.aws.amazon.com/eks/latest/userguide/cluster-auth.html
def _get_eks_bearer_token(sts_client: boto3.client, cluster_name: str) -> str:  # type: ignore[valid-type]
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


def get_k8s_client(use_tournament_account: bool = False) -> client.BatchV1Api:
    if not use_tournament_account:
        return _get_local_or_incluster_client()

    cfg = get_dispatch_config()
    if not cfg.EVAL_CLUSTER_ROLE_ARN or not cfg.EVAL_CLUSTER_NAME:
        raise ValueError("EVAL_CLUSTER_ROLE_ARN and EVAL_CLUSTER_NAME must be set")
    assumed = boto3.client("sts").assume_role(
        RoleArn=cfg.EVAL_CLUSTER_ROLE_ARN,
        RoleSessionName="dispatcher-eval-access",
        ExternalId=cfg.EVAL_CLUSTER_EXTERNAL_ID,
    )
    creds = assumed["Credentials"]

    region = cfg.EVAL_CLUSTER_REGION
    assumed_creds = dict(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
    )

    eks = boto3.client("eks", region_name=region, **assumed_creds)
    cluster = eks.describe_cluster(name=cfg.EVAL_CLUSTER_NAME)["cluster"]

    sts_assumed = boto3.client("sts", region_name=region, **assumed_creds)
    token = _get_eks_bearer_token(sts_assumed, cfg.EVAL_CLUSTER_NAME)

    ca_file = tempfile.NamedTemporaryFile(delete=False, suffix=".crt")
    ca_file.write(base64.b64decode(cluster["certificateAuthority"]["data"]))
    ca_file.close()

    configuration = Configuration()
    configuration.host = cluster["endpoint"]
    configuration.ssl_ca_cert = ca_file.name  # type: ignore
    configuration.api_key = {"authorization": f"Bearer {token}"}
    return client.BatchV1Api(ApiClient(configuration))


@functools.cache
def _get_local_or_incluster_client() -> client.BatchV1Api:
    cfg = get_dispatch_config()

    if cfg.LOCAL_DEV:
        if not cfg.LOCAL_DEV_K8S_CONTEXT:
            raise ValueError("LOCAL_DEV=true requires LOCAL_DEV_K8S_CONTEXT to be set")
        load_kube_config(context=cfg.LOCAL_DEV_K8S_CONTEXT)
    else:
        load_incluster_config()

    return client.BatchV1Api()


def dispatch_job(
    job: JobRequest, use_tournament_account: bool = False, policy_s3_keys: dict[int, str] | None = None
) -> str:
    if job.job_type == JobType.episode:
        return create_episode_job(job, use_tournament_account, policy_s3_keys or {})
    raise ValueError(f"Unknown job type: {job.job_type}")


def create_episode_job(
    job: JobRequest, use_tournament_account: bool = False, policy_s3_keys: dict[int, str] | None = None
) -> str:
    cfg = get_dispatch_config()
    batch_v1 = get_k8s_client(use_tournament_account)
    job_name = f"job-{job.id.hex[:8]}"

    env_vars: list[client.V1EnvVar] = []

    if use_tournament_account:
        if not cfg.POLICY_S3_BUCKET or not cfg.EVAL_S3_BUCKET:
            raise ValueError("POLICY_S3_BUCKET must be set when EVAL_S3_BUCKET is configured")
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

        prefix = f"jobs/{job.id}"
        s3_client = boto3.client("s3")
        spec_key = f"{prefix}/spec.json"
        s3_client.put_object(
            Bucket=cfg.EVAL_S3_BUCKET,
            Key=spec_key,
            Body=json.dumps(job_spec).encode("utf-8"),
            ContentType="application/json",
        )
        spec_uri = presign_operation("get", cfg.EVAL_S3_BUCKET, spec_key, exp, endpoint)
        results_uri = presign_operation("put", cfg.EVAL_S3_BUCKET, f"{prefix}/results.json", exp, endpoint)
        replay_uri = presign_operation("put", cfg.EVAL_S3_BUCKET, f"{prefix}/replay.json.z", exp, endpoint)
        env_vars = [
            client.V1EnvVar(name="JOB_SPEC_URI", value=spec_uri),
            client.V1EnvVar(name="RESULTS_URI", value=results_uri),
            client.V1EnvVar(name="REPLAY_URI", value=replay_uri),
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


def presign_operation(
    operation: Literal["get", "put"], bucket: str, key: str, expiration: int, endpoint: str | None
) -> str:
    s3_client = boto3.client("s3", **({"endpoint_url": endpoint} if endpoint else {}))
    return s3_client.generate_presigned_url(
        f"{operation}_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expiration,
    )
