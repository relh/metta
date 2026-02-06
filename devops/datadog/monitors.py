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
    - monitoring namespace: datadog agent and other infra pods
    - skypilot-monitor*: expected to crash when no skypilot cluster exists
    - pr-similarity-cache-*: transient job pods
    """

    exclude_tags = ", ".join(
        [
            "!kube_namespace:monitoring",
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
        "query": "avg(last_5m):sum:job.outstanding_count{service:observatory-backend} > 180",
        "message": (
            "{{value}} outstanding jobs (limit: 200). Jobs may be processing slowly or failing.\n\n"
            "Check: https://observatory.softmax-research.net/episode-jobs\n\n"
            f"{WEBHOOK_DISCORD}"
        ),
        "tags": ["env:production", "team:infra", "managed-by:code", "service:tournament"],
        "priority": 3,
        "thresholds": {"critical": 180},
        "options": {
            "notify_no_data": False,
            "renotify_interval": 30,
            "include_tags": False,
        },
    }


def job_failure_rate_monitor() -> dict:
    """Monitor for high job failure rate (infrastructure/lifecycle errors only).

    Alerts when the rate of job failures is elevated, indicating systematic issues
    with infrastructure (OOM, timeouts, pod issues, etc). Excludes policy errors
    (policy spawn/registration failures) which are user errors, not infra issues.
    """
    return {
        "name": "[Tournament] High Job Failure Rate (Infrastructure)",
        "type": "query alert",
        "query": (
            "sum(last_15m):sum:job.state_transition{"
            "to_status:failed,!error_type:policy_error,service:observatory-backend"
            "}.as_count() > 20"
        ),
        "message": (
            "{{value}} infrastructure job failures in the last 15 minutes (excludes policy errors).\n\n"
            "Check error types in Datadog or: https://observatory.softmax-research.net/episode-jobs?status=failed\n\n"
            f"{WEBHOOK_DISCORD}"
        ),
        "tags": ["env:production", "team:infra", "managed-by:code", "service:tournament"],
        "priority": 2,
        "thresholds": {"critical": 20},
        "options": {
            "notify_no_data": False,
            "renotify_interval": 60,
            "include_tags": False,
        },
    }


def job_stuck_pending_monitor() -> dict:
    """Monitor for jobs stuck with very few running.

    Alerts when running jobs drops below 5 for sustained period while
    pending/dispatched jobs exist, indicating possible dispatch issues.
    """
    return {
        "name": "[Tournament] Low Running Jobs",
        "type": "query alert",
        "query": "avg(last_10m):avg:job.outstanding_count{status:running,service:observatory-backend} < 5",
        "message": (
            "Only {{value}} jobs running (avg over 10min). Check if jobs are stuck:\n\n"
            "Possible issues:\n"
            "- K8s node scaling problems\n"
            "- Job dispatcher issues\n"
            "- Resource constraints\n\n"
            "Check k8s pods: `kubectl get pods -n metta | grep episode`\n"
            "Check pending queue: https://observatory.softmax-research.net/episode-jobs?status=pending\n\n"
            f"{WEBHOOK_DISCORD}"
        ),
        "tags": ["env:production", "team:infra", "managed-by:code", "service:tournament"],
        "priority": 3,
        "thresholds": {"critical": 5, "warning": 10},
        "options": {
            "notify_no_data": False,
            "renotify_interval": 30,
            "include_tags": False,
            "require_full_window": True,
        },
    }


def job_lifecycle_failure_rate_monitor() -> dict:
    """Monitor for high job lifecycle failure rate (infrastructure/k8s issues).

    Alerts when >10% of jobs are failing due to lifecycle errors (pod_not_found,
    pod_deleted, result_missing, result_error) as opposed to episode runtime errors.
    Includes minimum volume guard to avoid false positives on low traffic.
    """
    return {
        "name": "[Tournament] High Job Lifecycle Failure Rate: {{value}}%",
        "type": "query alert",
        "query": (
            "sum(last_15m):"
            "(sum:job.state_transition{to_status:failed,"
            "error_type:(pod_not_found OR pod_deleted OR result_missing OR result_error),"
            "service:observatory-backend}.as_count() / "
            "(sum:job.state_transition{to_status:failed,service:observatory-backend}.as_count() + "
            "sum:job.state_transition{to_status:completed,service:observatory-backend}.as_count())) * 100 > 10 && "
            "sum(last_15m):sum:job.state_transition{to_status:failed,service:observatory-backend}.as_count() > 10"
        ),
        "message": (
            "{{value}}% of jobs failing due to infrastructure/lifecycle issues (>10 failures).\n\n"
            "This indicates K8s/pod/S3 problems, not episode runtime errors.\n\n"
            "Check: https://observatory.softmax-research.net/episode-jobs?status=failed\n"
            "Pod health: `kubectl get pods -n metta`\n\n"
            f"{WEBHOOK_DISCORD}"
        ),
        "tags": ["env:production", "team:infra", "managed-by:code", "service:tournament"],
        "priority": 2,
        "thresholds": {"critical": 15, "warning": 10},
        "options": {
            "notify_no_data": False,
            "renotify_interval": 60,
            "include_tags": False,
        },
    }


def job_high_oom_rate_monitor() -> dict:
    """Monitor for high OOM rate among failures.

    Alerts when >5% of job failures are due to OOM, indicating pods may need
    more memory or there's a memory leak. Includes minimum volume guard.
    """
    return {
        "name": "[Tournament] High OOM Rate: {{value}}% of failures",
        "type": "query alert",
        "query": (
            "sum(last_15m):"
            "(sum:job.state_transition{to_status:failed,error_type:oom,service:observatory-backend}.as_count() / "
            "sum:job.state_transition{to_status:failed,service:observatory-backend}.as_count()) * 100 > 5 && "
            "sum(last_15m):sum:job.state_transition{to_status:failed,service:observatory-backend}.as_count() > 10"
        ),
        "message": (
            "{{value}}% of job failures are OOM (threshold: 5%).\n\n"
            "Possible causes:\n"
            "- Pod memory limits too low\n"
            "- Memory leak in policy or environment\n"
            "- Large replay files not being cleaned up\n\n"
            "Check: https://observatory.softmax-research.net/episode-jobs?status=failed&error_type=oom\n\n"
            f"{WEBHOOK_DISCORD}"
        ),
        "tags": ["env:production", "team:infra", "managed-by:code", "service:tournament"],
        "priority": 2,
        "thresholds": {"critical": 10, "warning": 5},
        "options": {
            "notify_no_data": False,
            "renotify_interval": 60,
            "include_tags": False,
        },
    }


def job_high_pending_queue_monitor() -> dict:
    """Monitor for sustained high pending job count.

    Alerts when pending job queue is sustained above 50, indicating dispatch
    may be slower than job submission rate. Complements job_queue_buildup_monitor
    which tracks total outstanding jobs.
    """
    return {
        "name": "[Tournament] High Pending Queue: {{value}} pending",
        "type": "query alert",
        "query": "avg(last_10m):avg:job.outstanding_count{status:pending,service:observatory-backend} > 100",
        "message": (
            "{{value}} jobs pending (sustained >10min). Dispatch may be slower than submission rate.\n\n"
            "Check:\n"
            "- K8s node availability: `kubectl get nodes`\n"
            "- Job dispatcher health\n"
            "- https://observatory.softmax-research.net/episode-jobs?status=pending\n\n"
            f"{WEBHOOK_DISCORD}"
        ),
        "tags": ["env:production", "team:infra", "managed-by:code", "service:tournament"],
        "priority": 3,
        "thresholds": {"critical": 100},
        "options": {
            "notify_no_data": False,
            "renotify_interval": 30,
            "include_tags": False,
        },
    }


def job_slow_dispatch_monitor() -> dict:
    """Monitor for slow job dispatch times.

    Alerts when p95 dispatch time (pending -> running) exceeds 2 minutes,
    indicating K8s scheduling issues. Note: only measures completed dispatches.
    """
    return {
        "name": "[Tournament] Slow Job Dispatch: {{value}}s p95",
        "type": "query alert",
        "query": "avg(last_30m):p95:job.stage_duration{stage:dispatched,service:observatory-backend}",
        "message": (
            "P95 dispatch time is {{value}}s (threshold: 120s).\n\n"
            "Possible causes:\n"
            "- K8s node scaling issues\n"
            "- Resource constraints (CPU/memory/GPU unavailable)\n"
            "- Node pressure or scheduling delays\n\n"
            "Check: `kubectl get nodes` and `kubectl describe nodes`\n\n"
            f"{WEBHOOK_DISCORD}"
        ),
        "tags": ["env:production", "team:infra", "managed-by:code", "service:tournament"],
        "priority": 3,
        "thresholds": {"critical": 180, "warning": 120},
        "options": {
            "notify_no_data": False,
            "renotify_interval": 60,
            "include_tags": False,
        },
    }


def job_no_activity_monitor() -> dict:
    """Monitor for no job activity when tournament should be running.

    Alerts when no job state transitions have occurred in 10 minutes, indicating
    the tournament commissioner may have stopped creating jobs. This is an imprecise
    check that may alert during legitimate downtime, but catches stuck commissioners.
    """
    return {
        "name": "[Tournament] No Job Activity: {{value}} jobs in 10min",
        "type": "query alert",
        "query": ("sum(last_10m):sum:job.state_transition{service:observatory-backend}.as_count() < 1"),
        "message": (
            "No job state transitions in the last 10 minutes.\n\n"
            "Possible causes:\n"
            "- Tournament commissioner stopped or crashed\n"
            "- No active tournaments/qualifying pools scheduled\n"
            "- Database connectivity issues\n\n"
            "Check:\n"
            "- Commissioner logs: `kubectl logs -n metta -l app=tournament-commissioner`\n"
            "- Active tournaments: https://observatory.softmax-research.net/tournaments\n"
            "- DB connectivity\n\n"
            f"{WEBHOOK_DISCORD}"
        ),
        "tags": ["env:production", "team:infra", "managed-by:code", "service:tournament"],
        "priority": 3,
        "thresholds": {"critical": 1},
        "options": {
            "notify_no_data": True,
            "no_data_timeframe": 10,
            "renotify_interval": 60,
            "include_tags": False,
        },
    }


ALL_MONITORS = [
    k8s_deployment_replicas_monitor,
    k8s_crashloopbackoff_monitor,
    k8s_node_count_monitor,
    job_failure_rate_monitor,
    job_queue_buildup_monitor,
    job_high_pending_queue_monitor,
    # Removed to avoid false positives:
    # job_stuck_pending_monitor,  # Too noisy - depends on tournament schedule
    # job_no_activity_monitor,    # Alerts during legitimate downtime
    # TODO: Compound queries with && are not supported by Datadog monitor API.
    # These need to be created as composite monitors or restructured:
    # job_lifecycle_failure_rate_monitor,
    # job_high_oom_rate_monitor,
    # TODO: Percentile queries on this metric type are not supported:
    # job_slow_dispatch_monitor,
]


def get_all_monitor_configs() -> list[dict]:
    return [m() for m in ALL_MONITORS]
