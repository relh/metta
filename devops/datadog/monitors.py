"""Datadog monitor definitions as code.

To sync monitors: uv run python -m devops.datadog.cli monitors sync
To preview:       uv run python -m devops.datadog.cli monitors sync --dry-run
"""

from __future__ import annotations

WEBHOOK_DISCORD = "@webhook-Discord"


def k8s_deployment_replicas_monitor() -> dict:
    """Monitor for k8s deployment replica availability.

    Uses min(last_10m) instead of avg(last_5m) so we only alert if replicas have
    been unavailable for the ENTIRE 10-minute window. Brief outages during node
    rotation (typically <2 minutes) won't trigger false alarms.

    Excludes:
    - observatory-pr-*: PR preview for observatory
    - softmax-com-pr-*: PR preview for softmax.com
    """

    tags = ", ".join(
        [
            "env:production",
            "kube_cluster_name:main",
            "!kube_deployment:observatory-pr-*",
            "!kube_deployment:softmax-com-pr-*",
        ]
    )
    group_by = ", ".join(
        [
            "kube_cluster_name",
            "kube_namespace",
            "kube_deployment",
        ]
    )
    return {
        "name": "[Kubernetes] Deployment Replicas Down",
        "type": "query alert",
        "query": (
            "min(last_10m):"
            "avg:kubernetes_state.deployment.replicas_desired{" + tags + "} by {" + group_by + "} - "
            "avg:kubernetes_state.deployment.replicas_available{" + tags + "} by {" + group_by + "}"
            " >= 1"
        ),
        "message": (
            "Deployment {{kube_namespace.name}}/{{kube_deployment.name}} has had "
            "unavailable replicas for 10+ minutes.\n\n"
            f"{WEBHOOK_DISCORD}"
        ),
        "tags": ["env:production", "team:infra", "managed-by:code"],
        "priority": 3,
        "thresholds": {"critical": 1},
        "options": {
            "notify_no_data": False,
            "renotify_interval": 60,
            "evaluation_delay": 60,
            "include_tags": True,
            "new_group_delay": 300,
        },
    }


def k8s_crashloopbackoff_monitor() -> dict:
    """Monitor for pods stuck in CrashLoopBackOff.

    Uses max(last_10m) so brief restarts don't trigger - only fires if a pod has
    been in CrashLoopBackOff for the entire 10-minute window.

    Excludes:
    - skypilot-monitor*: expected to crash when no skypilot cluster exists
    - pr-similarity-cache-*: transient job pods
    """

    exclude_tags = ", ".join(
        [
            "!pod_name:skypilot-monitor*",
            "!pod_name:pr-similarity-cache-*",
            "!pod_name:observatory-pr-*",
            "!pod_name:softmax-com-pr-*",
        ]
    )

    return {
        "name": "[Kubernetes] Pod {{pod_name.name}} is CrashloopBackOff on namespace {{kube_namespace.name}}",
        "type": "query alert",
        "query": (
            "max(last_10m):default_zero("
            "max:kubernetes_state.container.status_report.count.waiting{"
            "reason:crashloopbackoff, " + exclude_tags + "} by {kube_cluster_name,kube_namespace,pod_name}"
            ") >= 1"
        ),
        "message": (
            "{{#is_alert}}\n"
            "{{pod_name.name}} in {{kube_namespace.name}} is in CrashLoopBackOff\n"
            "{{/is_alert}}\n"
            "{{#is_recovery}}\n"
            "{{pod_name.name}} recovered\n"
            "{{/is_recovery}}\n\n"
            f"{WEBHOOK_DISCORD}"
        ),
        "tags": ["env:production", "team:infra", "managed-by:code"],
        "priority": 2,
        "thresholds": {"critical": 1},
        "options": {
            "notify_no_data": False,
            "notify_audit": True,
            "include_tags": False,
            "new_group_delay": 60,
            "require_full_window": False,
        },
    }


def k8s_node_count_monitor() -> dict:
    """Monitor for excessive node count (cost protection).

    Alerts if average node count over the last day exceeds 200, which usually
    indicates runaway orchestrator scaling.
    """
    return {
        "name": "[Kubernetes] Too many nodes: {{value}}",
        "type": "query alert",
        "query": "avg(last_1d):avg:kubernetes_state.node.count{kube_cluster_name:main} > 200",
        "message": (
            "{{value}} nodes running. Investigate with `kubectl get nodes`, etc.\n\n"
            "Hint: likely caused by orchestrator; check running evals in observatory.\n\n"
            f"{WEBHOOK_DISCORD}"
        ),
        "tags": ["env:production", "team:infra", "managed-by:code"],
        "priority": 2,
        "thresholds": {"critical": 200},
        "options": {
            "notify_no_data": False,
            "include_tags": False,
            "new_host_delay": 300,
        },
    }


def job_queue_buildup_monitor() -> dict:
    """Monitor for job queue buildup approaching backpressure limit.

    Alerts when outstanding jobs (pending + dispatched + running) are building up,
    indicating the system can't process jobs fast enough. Backpressure kicks in at 200.
    """
    return {
        "name": "[Tournament] Job Queue Buildup: {{value}} outstanding",
        "type": "query alert",
        "query": ("avg(last_5m):sum:job.outstanding_count{service:observatory-backend} > 150"),
        "message": (
            "{{value}} outstanding jobs (limit: 200). Jobs may be processing slowly or failing.\n\n"
            "Check: https://observatory.softmax-research.net/episode-jobs\n\n"
            f"{WEBHOOK_DISCORD}"
        ),
        "tags": ["env:production", "team:infra", "managed-by:code", "service:tournament"],
        "priority": 3,
        "thresholds": {"critical": 180, "warning": 150},
        "options": {
            "notify_no_data": False,
            "renotify_interval": 30,
            "include_tags": False,
        },
    }


def job_failure_rate_monitor() -> dict:
    """Monitor for high job failure rate.

    Alerts when the rate of job failures is elevated, indicating systematic issues
    with job execution (OOM, policy errors, timeouts, etc).
    """
    return {
        "name": "[Tournament] High Job Failure Rate",
        "type": "query alert",
        "query": (
            "sum(last_15m):sum:job.state_transition{to_status:failed,service:observatory-backend}.as_count() > 10"
        ),
        "message": (
            "{{value}} jobs failed in the last 15 minutes.\n\n"
            "Check error types in Datadog or: https://observatory.softmax-research.net/episode-jobs?status=failed\n\n"
            f"{WEBHOOK_DISCORD}"
        ),
        "tags": ["env:production", "team:infra", "managed-by:code", "service:tournament"],
        "priority": 2,
        "thresholds": {"critical": 20, "warning": 10},
        "options": {
            "notify_no_data": False,
            "renotify_interval": 60,
            "include_tags": False,
        },
    }


def job_stuck_pending_monitor() -> dict:
    """Monitor for jobs stuck in pending/dispatched state.

    Alerts when there are pending or dispatched jobs but no running jobs,
    indicating the job runner may be stuck or k8s scheduling issues.
    """
    return {
        "name": "[Tournament] Jobs Stuck - No Running Jobs",
        "type": "query alert",
        "query": (
            "avg(last_10m):"
            "(sum:job.outstanding_count{status:pending,service:observatory-backend} + "
            "sum:job.outstanding_count{status:dispatched,service:observatory-backend}) - "
            "sum:job.outstanding_count{status:running,service:observatory-backend} > 5"
        ),
        "message": (
            "Jobs are queued but none are running. Possible issues:\n"
            "- K8s node scaling problems\n"
            "- Job dispatcher issues\n"
            "- Resource constraints\n\n"
            "Check k8s pods: `kubectl get pods -n metta | grep episode`\n\n"
            f"{WEBHOOK_DISCORD}"
        ),
        "tags": ["env:production", "team:infra", "managed-by:code", "service:tournament"],
        "priority": 2,
        "thresholds": {"critical": 5},
        "options": {
            "notify_no_data": False,
            "renotify_interval": 30,
            "include_tags": False,
            "require_full_window": True,
        },
    }


ALL_MONITORS = [
    k8s_deployment_replicas_monitor,
    k8s_crashloopbackoff_monitor,
    k8s_node_count_monitor,
    job_queue_buildup_monitor,
    job_failure_rate_monitor,
    job_stuck_pending_monitor,
]


def get_all_monitor_configs() -> list[dict]:
    return [m() for m in ALL_MONITORS]
