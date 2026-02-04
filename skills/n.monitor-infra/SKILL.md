---
name: n.monitor-infra
description:
  Monitor production infrastructure health - GitHub Actions builds, ECR image pushes, Helm deployments, and Kubernetes
  service status. Use when deploying, checking service health, debugging outages, or watching CI/CD pipelines.
---

# Infrastructure Monitoring

## Quick Health Check

```bash
# All services at a glance
kubectl --context main get deployments -n observatory
kubectl --context main get deployments -n orchestrator

# Hit health endpoints directly
curl -sf https://api.observatory.softmax-research.net/whoami
curl -sf https://observatory.softmax-research.net
curl -sf https://home.softmax-research.net
```

## Architecture

### EKS Clusters

| Context      | Account      | Purpose                                                   |
| ------------ | ------------ | --------------------------------------------------------- |
| `main`       | 751442549699 | All services (observatory, orchestrator, monitoring, etc) |
| `tournament` | 583928386201 | Episode runner jobs (eval workloads, isolated account)    |
| `orbstack`   | local        | Local dev cluster                                         |

### Production Services

```
Namespace: observatory
  observatory           (frontend)  -- observatory.softmax-research.net     (port 3000, 2 replicas)
  observatory-backend   (API)       -- api.observatory.softmax-research.net (port 8000, 2 replicas)

Namespace: orchestrator
  orchestrator-orchestrator  -- eval task dispatcher (1 replica)
  orchestrator-tournament    -- tournament commissioner (1 replica, Recreate strategy)
  orchestrator-watcher       -- K8s job watcher (1 replica)

Namespace: softmax-com
  softmax-com-frontend  -- softmax.com / softmax-com.softmax-research.net (2 replicas)

Namespace: monitoring
  datadog-cluster-agent

Namespace: skypilot
  skypilot-api-server, skypilot-oauth2-proxy
```

### Multi-Account Tournament Architecture

Evaluation jobs execute untrusted user-submitted policy code in an isolated AWS account. See
`docs/specs/0018-tournament-aws-account.md` for full design.

```
Primary account (751442549699)                Tournament account (583928386201)
  observatory-backend  ───IRSA + AssumeRole──>  EKS cluster "tournament"
  orchestrator-watcher ───IRSA + AssumeRole──>    namespace: jobs
  CI (GitHub Actions)  ───ECR cross-account──>    ECR: episode-runner
```

- **Dispatch**: Backend creates k8s Jobs in the tournament cluster's `jobs` namespace
- **Image**: CI retags `metta-policy-evaluator` from primary ECR into tournament ECR as `episode-runner`
- **Data**: Job pods get presigned S3 URLs (no IAM credentials in pods)
- **Watch**: Watcher polls tournament cluster pods, updates job status in backend

```bash
# Check eval jobs running in tournament cluster
kubectl --context tournament -n jobs get pods
kubectl --context tournament -n jobs get jobs

# Check job logs
kubectl --context tournament -n jobs logs <pod-name>
```

### ECR Registries

| Account      | Image                    | Used By                                                |
| ------------ | ------------------------ | ------------------------------------------------------ |
| 751442549699 | `metta-app-backend`      | observatory-backend                                    |
| 751442549699 | `metta-app-frontend`     | observatory (frontend)                                 |
| 751442549699 | `metta-policy-evaluator` | orchestrator (tournament, watcher, orchestrator)       |
| 583928386201 | `episode-runner`         | tournament eval jobs (retag of metta-policy-evaluator) |

## CI/CD Pipeline

### GitHub Actions Workflows

| Workflow                                | Triggers (on main)                                   | Deploys To                                |
| --------------------------------------- | ---------------------------------------------------- | ----------------------------------------- |
| Build Observatory Backend Docker Image  | `app_backend/` changes                               | `observatory` namespace                   |
| Build Observatory Frontend Docker Image | `app_backend/frontend/` changes                      | `observatory` namespace                   |
| Build Policy Evaluator Docker Image     | `app_backend/`, `metta/sim/`, `common/`, `packages/` | `orchestrator` namespace + tournament ECR |
| Build and deploy Softmax.com site       | Various frontend changes                             | `softmax-com` namespace                   |

### Deploy Flow

1. Push to `main` triggers build workflow
2. Workflow filters for relevant file changes (skips if no changes)
3. Builds Docker image, pushes to ECR with `sha-<full_commit_sha>` tag
4. Configures EKS access via OIDC role assumption
5. `helm upgrade` to production namespace
6. Policy evaluator additionally retags image to tournament account ECR as `episode-runner`

### Monitoring a Deploy

```bash
# Watch GitHub Actions in real time
gh run list --branch main --limit 5 --json workflowName,status,conclusion,databaseId

# Detailed job steps for a specific run
gh run view <RUN_ID> --json jobs

# Watch build logs live
gh run watch <RUN_ID>
```

## Kubernetes Monitoring

### Pod Health

```bash
# Check pod status (look for Error, CrashLoopBackOff, ImagePullBackOff)
kubectl --context main -n observatory get pods
kubectl --context main -n orchestrator get pods

# Recent events (surfaces scheduling issues, OOM kills, probe failures)
kubectl --context main -n observatory get events --sort-by=.lastTimestamp | tail -20
kubectl --context main -n orchestrator get events --sort-by=.lastTimestamp | tail -20

# Pod logs (current)
kubectl --context main -n observatory logs deployment/observatory-backend --tail=50
kubectl --context main -n orchestrator logs deployment/orchestrator-tournament --tail=50
kubectl --context main -n orchestrator logs deployment/orchestrator-watcher --tail=50

# Pod logs (previous crashed container)
kubectl --context main -n observatory logs deployment/observatory-backend --previous --tail=50
```

### Deployment Status

```bash
# Check rollout status (will report if stuck)
kubectl --context main -n observatory rollout status deployment/observatory-backend
kubectl --context main -n orchestrator rollout status deployment/orchestrator-tournament

# See current image SHA
kubectl --context main -n observatory get deployment observatory-backend -o jsonpath='{.spec.template.spec.containers[0].image}' && echo
kubectl --context main -n orchestrator get deployment orchestrator-tournament -o jsonpath='{.spec.template.spec.containers[0].image}' && echo

# Verify a specific commit is deployed
# Image tags are sha-<full_commit_sha>
git log --oneline <sha> -1
```

### Health Probes

| Service             | Probe Endpoint     | Startup      | Liveness | Readiness |
| ------------------- | ------------------ | ------------ | -------- | --------- |
| observatory-backend | `/whoami` :8000    | 5min (60x5s) | 3x10s    | 2x5s      |
| observatory         | `/` :3000          | default      | 3x10s    | 3x10s     |
| tournament          | `/healthz` :health | none         | 3x30s    | none      |
| watcher             | `/healthz` :health | none         | 3x30s    | none      |
| orchestrator        | none               | none         | none     | none      |

Tournament and watcher use a standalone health server (`:health` named port) that checks an internal heartbeat loop. The
`/healthz` endpoint returns 503 if the main loop hasn't sent a heartbeat in 120s.

### Verifying Services Are Actually Running

Pods showing `Running 1/1` only means the health probe passed. Check logs to confirm the service loop is actively
working.

**Tournament** -- cycles through seasons. Healthy logs show repeated cycles:

```bash
kubectl --context main -n orchestrator logs deployment/orchestrator-tournament --tail=30

# Healthy output pattern (season names will vary):
# [timestamp] INFO [<season>] pool=competition players=N match_combos=N
# [timestamp] INFO [<season>] pool=competition matches_to_schedule=N
# [timestamp] INFO [<season>] scheduling done, getting membership changes
# [timestamp] INFO [<season>] membership changes=N
# [timestamp] INFO [<season>] cycle complete

# Red flags:
# - No log output (stuck or deadlocked)
# - Repeated exceptions or tracebacks
# - "cycle complete" stops appearing (loop died)
# - rss growing unbounded (memory leak, will eventually OOM)
```

Each season cycles through: `_sync_match_scores` -> pool checks (qualifying, competition) -> scheduling -> membership
changes -> cycle complete.

Key fields in logs:

- `players=N` -- how many policies are in the pool
- `match_combos=N` -- possible matchups
- `matches_to_schedule=N` -- new matches to dispatch (0 when caught up)
- `outstanding=N slots=N` -- running matches vs available capacity
- `rss=NMi` -- memory usage (watch for growth)

**Watcher** -- polls k8s pods every ~30s. Healthy logs show a steady heartbeat:

```bash
kubectl --context main -n orchestrator logs deployment/orchestrator-watcher --tail=20

# Healthy output pattern:
# [timestamp] INFO Starting pod watch on cluster=eval from resourceVersion=NNNNNN
# (repeats every ~30s with incrementing resourceVersion)

# Red flags:
# - resourceVersion not incrementing (stuck watch)
# - Connection errors or timeouts (cluster unreachable)
# - No output at all (process died but health check hasn't caught it yet)
```

**Orchestrator** -- dispatches eval jobs. Mostly quiet when idle:

```bash
kubectl --context main -n orchestrator logs deployment/orchestrator-orchestrator --tail=20

# On startup:
# INFO: Datadog tracing enabled: service=eval-orchestrator
# INFO: Backend URL: <url>
# INFO: Task timeout: 210.0 minutes
# INFO: Orchestrator startup trace

# When active, look for job dispatch/completion messages
```

**Observatory backend** -- API server, best checked via endpoints:

```bash
# Health
curl -sf https://api.observatory.softmax-research.net/whoami

# Check recent logs for errors
kubectl --context main -n observatory logs deployment/observatory-backend --tail=50

# Watch for migration issues on startup
kubectl --context main -n observatory logs deployment/observatory-backend --tail=100 | grep -i "migration\|error\|traceback"
```

## Datadog

### Cluster Agent Config

- Cluster name: `main`
- APM: port 8126
- OTLP metrics: HTTP port 4318, gRPC port 4317
- Log collection: all containers
- Pod labels: `tags.datadoghq.com/{env,service,version}`

### Querying Datadog API

The Datadog API key is stored in AWS Secrets Manager:

```python
from softmax.aws.secrets_manager import get_secretsmanager_secret
api_key = get_secretsmanager_secret("datadog/api-key")
```

```bash
# Query via curl (get API key from secrets manager first)
DD_API_KEY=$(python3 -c "from softmax.aws.secrets_manager import get_secretsmanager_secret; print(get_secretsmanager_secret('datadog/api-key'))")

# List monitors in alert state
curl -s -H "DD-API-KEY: $DD_API_KEY" \
  -H "DD-APPLICATION-KEY: <app-key>" \
  "https://api.datadoghq.com/api/v1/monitor?monitor_tags=env:production"

# Search logs
curl -s -H "DD-API-KEY: $DD_API_KEY" \
  -H "DD-APPLICATION-KEY: <app-key>" \
  "https://api.datadoghq.com/api/v2/logs/events/search" \
  -d '{"filter":{"query":"service:observatory-backend status:error","from":"now-1h"}}'
```

### Monitors (defined as code)

- `[Kubernetes] Deployment Replicas Down` -- alerts if replicas unavailable >10 min
- `[Kubernetes] CrashLoopBackOff Detection` -- pod restart loops
- Excludes PR preview deployments (`observatory-pr-*`, `softmax-com-pr-*`)

Config: `devops/helm.values/datadog-monitors.yaml`

## Database

Production uses AWS RDS (`main-pg.*.us-east-1.rds.amazonaws.com`). The connection string is in the
`observatory-backend-env` k8s secret as `STATS_DB_URI`.

Server runs migrations on startup (`RUN_MIGRATIONS=true`).

## PR Preview Environments

GitHub Actions creates preview deployments for PRs:

```bash
# List active PR previews
kubectl --context main -n observatory get deployments | grep "pr-"

# Preview URLs follow pattern:
# observatory-preview-<PR_NUMBER>.softmax-research.net

# Clean up stale previews (normally auto-deleted on PR close)
kubectl --context main -n observatory delete deployment observatory-pr-<NUMBER>
```

## Common Issues

### Build stuck / slow

Docker image builds can take 10-20 minutes for policy-evaluator (large image with ML deps). Check the GitHub Actions
step "Build Docker image" -- this is the slow step.

### Deploy succeeded but pods not updating

```bash
# Check if new replicaset was created
kubectl --context main -n observatory describe deployment observatory-backend | grep -A5 "NewReplicaSet"

# Old pods in Error state are normal -- they're from previous replicasets being scaled down
# Only worry about Error pods with the LATEST replicaset hash
```

### Service unreachable after deploy

1. Check pod readiness: `kubectl --context main -n observatory get pods`
2. Check events: `kubectl --context main -n observatory get events --sort-by=.lastTimestamp`
3. Check ingress: `kubectl --context main -n observatory get ingress`
4. Check service endpoints: `kubectl --context main -n observatory get endpoints`

### Tournament/watcher init container stuck

Both tournament and watcher have an init container `wait-for-backend` that curls
`https://api.observatory.softmax-research.net/whoami`. If the backend is down, these pods will hang in `Init:0/1` state.

### No eval jobs running

If tournament logs show `matches_to_schedule=N` (N>0) but no jobs appear in the tournament cluster:

```bash
# Check if orchestrator is dispatching
kubectl --context main -n orchestrator logs deployment/orchestrator-orchestrator --tail=50

# Check tournament cluster for stuck/failed jobs
kubectl --context tournament -n jobs get pods --sort-by=.metadata.creationTimestamp
kubectl --context tournament -n jobs get events --sort-by=.lastTimestamp | tail -20
```

## Key Files

| Area                     | Path                                                 |
| ------------------------ | ---------------------------------------------------- |
| Backend build workflow   | `.github/workflows/build-app-backend-image.yml`      |
| Frontend build workflow  | `.github/workflows/build-observatory-image.yml`      |
| Policy eval workflow     | `.github/workflows/build-policy-evaluator-image.yml` |
| Reusable deploy template | `.github/workflows/_build-and-deploy.yml`            |
| Docker build action      | `.github/actions/docker-build/action.yml`            |
| EKS configure action     | `.github/actions/eks-configure/action.yml`           |
| Helm chart: backend      | `devops/charts/observatory-backend/`                 |
| Helm chart: frontend     | `devops/charts/observatory/`                         |
| Helm chart: orchestrator | `devops/charts/orchestrator/`                        |
| Helmfile                 | `devops/helmfile.yaml`                               |
| Datadog config           | `devops/helm.values/datadog-values.yaml`             |
| Datadog monitors         | `devops/helm.values/datadog-monitors.yaml`           |
| Health server            | `app_backend/src/metta/app_backend/health_server.py` |
| Server startup           | `app_backend/src/metta/app_backend/server.py`        |
| Tournament account spec  | `docs/specs/0018-tournament-aws-account.md`          |
| Terraform: tournament    | `devops/tf/tournament/`                              |
| Terraform: EKS (IRSA)    | `devops/tf/eks/`                                     |
| Datadog agent setup      | `metta/setup/components/datadog_agent.py`            |
