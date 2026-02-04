---
name: n.debug-jobs
description:
  Debug episode evaluation job failures (OOMKilled, timeouts, S3 errors, missing results). Use when jobs in the
  tournament system fail or produce unexpected results.
---

# Debug Episode Jobs

## Architecture

```
app_backend/src/metta/app_backend/job_runner/
├── dispatcher.py         # Creates k8s jobs, presigned URLs
├── watcher.py            # Monitors jobs, fetches results from S3
├── tournament_cluster.py # Cluster connection/config
└── job_artifacts.py      # S3 artifact handling
```

**Flow:** Dispatcher creates job with presigned GET URLs (policy, job spec) and PUT URLs (results) → K8s runs
`Dockerfile.policy_evaluator` → Episode runner writes results to S3 → Watcher reads results, updates DB

**K8s namespace:** `jobs`

## Common Failures

| Symptom       | Check                              | Fix                                                                  |
| ------------- | ---------------------------------- | -------------------------------------------------------------------- |
| OOMKilled     | `kubectl describe pod -n jobs`     | Increase memory limits in dispatcher or optimize policy              |
| Timeout       | Episode runner logs                | Check `pure_single_episode_runner.py` timeout, policy infinite loops |
| S3 read error | Watcher logs, presigned URL expiry | Check cross-account IAM, URL signing                                 |
| "No results"  | S3 bucket contents                 | Check episode runner wrote to presigned PUT URL                      |
| Git fetch 128 | Repo auth                          | Check mettabox git credentials, repo visibility                      |

## Diagnostic Commands

```bash
# Pod status and events
kubectl --context tournament get pods -n jobs
kubectl --context tournament describe pod <pod-name> -n jobs
kubectl --context tournament logs <pod-name> -n jobs

# Recent failed jobs
kubectl --context tournament get pods -n jobs --field-selector=status.phase=Failed

# Check job spec (from dispatcher)
kubectl --context tournament get job <job-name> -n jobs -o yaml
```

## Key Files

- `devops/docker/Dockerfile.policy_evaluator` - Container that runs episodes
- `packages/mettagrid/python/src/mettagrid/runner/pure_single_episode_runner.py` - Episode execution
- `devops/tf/tournament/` - Tournament cluster terraform

## Cross-Account Context

Tournament runs in a separate AWS account. Presigned URLs enable cross-account S3 access without shared credentials.

**If presigned URLs fail:** Check IAM roles in `devops/tf/tournament/`, verify the policy-evaluator role has S3
permissions.
