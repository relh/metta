"""Datadog monitor definitions as code.

To sync monitors: uv run python -m devops.datadog.cli monitors sync
To preview:       uv run python -m devops.datadog.cli monitors sync --dry-run
"""

from __future__ import annotations

from devops.stable.stable_check_groups import StableCheckGroup
from devops.stable.stable_check_lifecycle import StableCheckLifecycle
from devops.stable.stable_check_metrics import (
    STABLE_CHECK_COMPLETED_AT_METRIC,
    STABLE_CHECK_EFFECTIVE_STATUS_SERVICE_CHECK,
    job_path_to_job_tag,
)
from devops.stable.stable_check_registry import discover_stable_checks

WEBHOOK_DISCORD = "@webhook-Discord"
WEBHOOK_ONCALL = "@oncall-on-call"
WEBHOOK_STABLE_ALERTS = f"{WEBHOOK_DISCORD} {WEBHOOK_ONCALL}"

STABLE_STALE_HOURS = 28
STABLE_STALE_QUERY_LOOKBACK = f"last_{STABLE_STALE_HOURS}h"
STABLE_FAILED_SERVICE_CHECK_LAST_COUNT = 1


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
    indicating the system can't process jobs fast enough. Backpressure kicks in at 300.
    """
    return {
        "name": "[Tournament] Job Queue Buildup: {{value}} outstanding",
        "type": "query alert",
        "query": "avg(last_5m):sum:job.outstanding_count{service:observatory-backend} > 280",
        "message": (
            "{{value}} outstanding jobs (limit: 300). Jobs may be processing slowly or failing.\n\n"
            "Check: https://observatory.softmax-research.net/episode-jobs\n\n"
            f"{WEBHOOK_DISCORD}"
        ),
        "tags": [
            "env:production",
            "team:infra",
            "managed-by:code",
            "service:tournament",
        ],
        "priority": 3,
        "thresholds": {"critical": 280},
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
            "to_status:failed,!error_type:policy_error,!error_type:config_error,service:observatory-backend"
            "}.as_count() > 20"
        ),
        "message": (
            "{{value}} infrastructure job failures in the last 15 minutes (excludes policy and config errors).\n\n"
            "Check error types in Datadog or: https://observatory.softmax-research.net/episode-jobs?status=failed\n\n"
            f"{WEBHOOK_DISCORD}"
        ),
        "tags": [
            "env:production",
            "team:infra",
            "managed-by:code",
            "service:tournament",
        ],
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
        "tags": [
            "env:production",
            "team:infra",
            "managed-by:code",
            "service:tournament",
        ],
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
        "tags": [
            "env:production",
            "team:infra",
            "managed-by:code",
            "service:tournament",
        ],
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
        "tags": [
            "env:production",
            "team:infra",
            "managed-by:code",
            "service:tournament",
        ],
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
        "tags": [
            "env:production",
            "team:infra",
            "managed-by:code",
            "service:tournament",
        ],
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
        "tags": [
            "env:production",
            "team:infra",
            "managed-by:code",
            "service:tournament",
        ],
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
        "tags": [
            "env:production",
            "team:infra",
            "managed-by:code",
            "service:tournament",
        ],
        "priority": 3,
        "thresholds": {"critical": 1},
        "options": {
            "notify_no_data": True,
            "no_data_timeframe": 10,
            "renotify_interval": 60,
            "include_tags": False,
        },
    }


def job_daily_cost_monitor() -> dict:
    """Monitor for daily job compute cost exceeding budget.

    Alerts when cumulative job cost over the last day exceeds $10k, indicating
    runaway eval scaling or unexpectedly long-running jobs.
    """
    return {
        "name": "[Tournament] Daily Job Cost: ${{value}}",
        "type": "query alert",
        "query": "sum(last_1d):sum:job.cost{service:observatory-backend}.as_count() > 10000",
        "message": (
            "${{value}} spent on job compute in the last 24 hours (limit: $10,000).\n\n"
            "Check:\n"
            "- Running evals: https://observatory.softmax-research.net/episode-jobs?status=running\n"
            "- Node count: `kubectl get nodes | wc -l`\n"
            "- Consider pausing tournaments if spend is unexpected\n\n"
            f"{WEBHOOK_DISCORD}"
        ),
        "tags": [
            "env:production",
            "team:infra",
            "managed-by:code",
            "service:tournament",
        ],
        "priority": 2,
        "thresholds": {"critical": 10000, "warning": 8000},
        "options": {
            "notify_no_data": False,
            "renotify_interval": 60,
            "include_tags": False,
        },
    }


def episode_length_spike_monitor() -> dict:
    """Monitor for sustained episode-length spikes in episode jobs."""
    return {
        "name": "[Tournament] Episode Length Spike: {{value}} avg steps",
        "type": "query alert",
        "query": "avg(last_10m):avg:episode.length{service:observatory-backend,job_type:episode} > 11000",
        "message": (
            "Average episode length is {{value}} steps over the last 10 minutes.\n\n"
            "Normal baseline is ~8k-10k steps. A sustained spike can indicate environment or rollout regressions.\n\n"
            "Check: https://observatory.softmax-research.net/episode-jobs\n\n"
            f"{WEBHOOK_DISCORD}"
        ),
        "tags": ["env:production", "team:infra", "managed-by:code", "service:tournament"],
        "priority": 3,
        "thresholds": {"critical": 11000},
        "options": {
            "notify_no_data": False,
            "renotify_interval": 60,
            "include_tags": False,
            "require_full_window": True,
        },
    }


def job_config_error_monitor() -> dict:
    """Monitor for config/validation errors indicating runner image is out of date."""
    return {
        "name": "[Tournament] Config Validation Errors",
        "type": "query alert",
        "query": (
            "sum(last_15m):sum:job.state_transition{"
            "to_status:failed,error_type:config_error,service:observatory-backend"
            "}.as_count() > 10"
        ),
        "message": (
            "{{value}} config validation errors in the last 15 minutes.\n\n"
            "This usually means the episode-runner image is out of date and doesn't "
            "recognize new config fields. Rebuild and redeploy the runner image.\n\n"
            "Check: https://observatory.softmax-research.net/episode-jobs?status=failed\n\n"
            f"{WEBHOOK_DISCORD}"
        ),
        "tags": [
            "env:production",
            "team:infra",
            "managed-by:code",
            "service:tournament",
        ],
        "priority": 3,
        "thresholds": {"critical": 10},
        "options": {
            "notify_no_data": False,
            "renotify_interval": 60,
            "include_tags": False,
        },
    }


def job_total_failure_rate_monitor() -> dict:
    """Monitor for total job failure rate (all error types)."""
    return {
        "name": "[Tournament] High Job Failure Rate",
        "type": "query alert",
        "query": (
            "sum(last_15m):sum:job.state_transition{to_status:failed,service:observatory-backend}.as_count() > 50"
        ),
        "message": (
            "{{value}} total job failures in the last 15 minutes (all error types).\n\n"
            "Check specific monitors for breakdown by error type (infra, config).\n\n"
            "Check: https://observatory.softmax-research.net/episode-jobs?status=failed\n\n"
            f"{WEBHOOK_DISCORD}"
        ),
        "tags": [
            "env:production",
            "team:infra",
            "managed-by:code",
            "service:tournament",
        ],
        "priority": 3,
        "thresholds": {"critical": 50},
        "options": {
            "notify_no_data": False,
            "renotify_interval": 60,
            "include_tags": False,
        },
    }


def episode_recording_failure_monitor() -> dict:
    """Monitor for episode recording failures in the event processor.

    Fires when the event processor successfully receives results from a pod but
    fails to write them to observatory (e.g. due to schema changes, S3 errors).
    Jobs end up marked completed but with no episode/replay data stored.
    """
    return {
        "name": "[Tournament] Episode Recording Failures",
        "type": "log alert",
        "query": (
            'logs("service:k8s-event-processor \\"Failed to record episode for job\\"").index("*")'
            '.rollup("count").last("5m") > 3'
        ),
        "message": (
            "{{value}} episode recording failures in the last 5 minutes.\n\n"
            "Jobs are completing but episode/replay data is NOT being saved to observatory. "
            "This is a silent data loss — users won't see results.\n\n"
            "Common causes:\n"
            "- Schema validation error (mettagrid/cogames update changed job fields)\n"
            "- S3 write failure\n"
            "- DuckDB error during bulk upload\n\n"
            "Check k8s-event-processor logs for the full traceback.\n\n"
            f"{WEBHOOK_DISCORD}"
        ),
        "tags": [
            "env:production",
            "team:infra",
            "managed-by:code",
            "service:tournament",
        ],
        "priority": 2,
        "thresholds": {"critical": 3},
        "options": {
            "notify_no_data": False,
            "renotify_interval": 30,
            "include_tags": False,
        },
    }


ALL_MONITORS = [
    k8s_deployment_replicas_monitor,
    k8s_crashloopbackoff_monitor,
    k8s_node_count_monitor,
    job_failure_rate_monitor,
    job_config_error_monitor,
    job_total_failure_rate_monitor,
    episode_recording_failure_monitor,
    job_queue_buildup_monitor,
    job_high_pending_queue_monitor,
    job_daily_cost_monitor,
    episode_length_spike_monitor,
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


def _stable_runner_stale_monitor(job_tag: str) -> dict:
    return {
        "name": f"[Stable] {job_tag} stale ({STABLE_STALE_HOURS}h)",
        "type": "query alert",
        "query": (
            f"avg({STABLE_STALE_QUERY_LOOKBACK}):"
            f"default_zero(avg:{STABLE_CHECK_COMPLETED_AT_METRIC}{{job:{job_tag}}}) < 1"
        ),
        "message": (
            f"No stable run reported for `{job_tag}` in the last {STABLE_STALE_HOURS} hours.\n\n{WEBHOOK_STABLE_ALERTS}"
        ),
        "tags": [
            "team:infra",
            "managed-by:code",
            "service:stable-runner",
            "scope:testing",
            f"stable_job:{job_tag}",
        ],
        "priority": 3,
        "thresholds": {"critical": 1},
        "options": {
            "notify_no_data": False,
            "require_full_window": False,
            "renotify_interval": 120,
            "include_tags": True,
        },
    }


def _stable_runner_failed_monitor(job_tag: str) -> dict:
    return {
        "name": f"[Stable] {job_tag} latest failed",
        "type": "service check",
        "query": (
            f'"{STABLE_CHECK_EFFECTIVE_STATUS_SERVICE_CHECK}".over("job:{job_tag}").by("job")'
            f".last({STABLE_FAILED_SERVICE_CHECK_LAST_COUNT}).count_by_status()"
        ),
        "message": (f"Latest stable run for `{job_tag}` is failed.\n\n{WEBHOOK_STABLE_ALERTS}"),
        "tags": [
            "team:infra",
            "managed-by:code",
            "service:stable-runner",
            "scope:testing",
            f"stable_job:{job_tag}",
        ],
        "priority": 2,
        "thresholds": {"critical": 1},
        "options": {
            "notify_no_data": False,
            "renotify_interval": 120,
            "include_tags": True,
        },
    }


def _should_create_stable_monitors(check: object) -> bool:
    lifecycle = getattr(check, "lifecycle", None)
    if lifecycle is not StableCheckLifecycle.ACTIVE:
        return False
    check_group = getattr(check, "check_group", None)
    if check_group is StableCheckGroup.INTERNAL_TRAINING_HEAVY:
        return False
    return True


def get_all_monitor_configs() -> list[dict]:
    configs = [m() for m in ALL_MONITORS]
    for check in discover_stable_checks():
        if not _should_create_stable_monitors(check):
            continue
        check_path = f"{check.func.__module__}.{check.func.__name__}"
        job_tag = job_path_to_job_tag(check_path)
        configs.append(_stable_runner_stale_monitor(job_tag))
        configs.append(_stable_runner_failed_monitor(job_tag))
    return configs
