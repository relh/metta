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
    """
    return {
        "name": "[Kubernetes] Deployment Replicas Down",
        "type": "query alert",
        "query": (
            "min(last_10m):"
            "avg:kubernetes_state.deployment.replicas_desired{env:production, kube_cluster_name:main} "
            "by {kube_cluster_name,kube_namespace,kube_deployment} - "
            "avg:kubernetes_state.deployment.replicas_available{env:production, kube_cluster_name:main} "
            "by {kube_cluster_name,kube_namespace,kube_deployment} >= 1"
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
    return {
        "name": "[Kubernetes] Pod {{pod_name.name}} is CrashloopBackOff on namespace {{kube_namespace.name}}",
        "type": "query alert",
        "query": (
            "max(last_10m):default_zero("
            "max:kubernetes_state.container.status_report.count.waiting{"
            "reason:crashloopbackoff, "
            "!pod_name:skypilot-monitor*, "
            "!pod_name:pr-similarity-cache-*"
            "} by {kube_cluster_name,kube_namespace,pod_name}"
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


ALL_MONITORS = [
    k8s_deployment_replicas_monitor,
    k8s_crashloopbackoff_monitor,
    k8s_node_count_monitor,
]


def get_all_monitor_configs() -> list[dict]:
    return [m() for m in ALL_MONITORS]
