from functools import lru_cache

from pydantic_settings import BaseSettings

LABEL_APP = "app"
LABEL_APP_VALUE = "episode-runner"
LABEL_JOB_ID = "job-id"


class JobDispatchConfig(BaseSettings):
    EPISODE_RUNNER_IMAGE: str = ""
    STATS_SERVER_URI: str = ""
    JOB_NAMESPACE: str = "jobs"
    # TODO: limit the scope of this to only update the job in question
    MACHINE_TOKEN: str = ""

    # Local dev mode: enables kube_config loading and volume mounts
    # When False (prod), requires in-cluster config - no silent fallback
    LOCAL_DEV: bool = False
    # Required when LOCAL_DEV=True: validates we're using the right k8s context
    LOCAL_DEV_K8S_CONTEXT: str = ""
    # Optional volume mounts for hot-reloading code in job pods
    # Format: comma-separated host:container pairs, e.g. "~/.aws:/root/.aws"
    LOCAL_DEV_MOUNTS: str = ""
    LOCAL_DEV_AWS_PROFILE: str = ""

    # S3 bucket for job artifacts (specs, results, replays)
    EVAL_S3_BUCKET: str = ""
    # S3 bucket where uploaded policies are stored
    POLICY_S3_BUCKET: str | None = None
    # Alternate S3 endpoint for generating presigned URLs (e.g. host.docker.internal
    # for local dev where pods can't use localhost). Direct S3 ops use AWS_ENDPOINT_URL.
    S3_PRESIGNED_ENDPOINT: str | None = None

    # Cross-account eval cluster access
    # When set, dispatcher assumes this role to access the eval EKS cluster
    EVAL_CLUSTER_NAME: str = ""
    EVAL_CLUSTER_REGION: str = "us-east-1"
    EVAL_CLUSTER_ROLE_ARN: str = ""
    EVAL_CLUSTER_EXTERNAL_ID: str = "tournament-eval-access"


@lru_cache
def get_dispatch_config() -> JobDispatchConfig:
    return JobDispatchConfig()
