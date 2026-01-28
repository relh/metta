# Job Runner

> **Status:** Implemented **Author:** Rhys, Nishad **Created:** 2026-01-15 **Updated:** 2026-01-28

## Summary

Define the job runner architecture for executing evaluation jobs with untrusted user-submitted policy code in a
dedicated AWS account, using presigned S3 GET/PUT URLs for all job I/O.

## Problem

### Previous system (pre-2026-01-28)

We initially moved to a job running system like so:

- Client submits job request to Observatory Backend
  - Postgres. See current (job params, status, timestamps, results)
  - EKS Cluster → k8s job. Not fargate yet so that it's easier to test locally
- Job runs
  - single_episode_runner is the entrypoint; it fetches job spec from observatory via provided id, spawns the "pure" (no
    side effect) runner
  - "Pure" runner first (impurely) loads policies from s3, then with network disabled (python sockets disabled), runs
    the episode as described in the on-fs spec handed to it from single_episode_runner
  - single_episode_runner observes results and uploads them to Observatory via API
- Watch process, subscribing to K8s job events, updates status of postgres row as job progresses (via observatory API)
- Client queries observatory backend about job status

### Issues with this

This works ok! But among other things, the jobs (and thus user-submitted code) are being executed in the same k8s
cluster and AWS account as everything else we have.

The job runner also has access to a long-lived observatory token.

The python socket disabling is only to catch accidental regressions; sidestepping it is possible.

## Goals

- Run evaluation jobs in a dedicated AWS account separate from primary infrastructure
- Jobs don't submit their own results or pull inputs from Observatory APIs
- Hot pool of pre-warmed nodes with per-job pod teardown (~5-10s startup target, one node per pod)

## Non-goals

- Airtight policy isolation (policies may tamper with games, each other, or cluster)
- Attribution of which policies cause OOMs or crashes
- Complete network isolation (policies may still reach the internet)
- Running policies as distinct docker images
- Performance targets (dollars or time per episode)

## Solution

### Architecture Overview

```
Primary Account                                    Eval Account
┌────────────────────────────────────────────┐    ┌──────────────────────────┐
│                                            │    │                          │
│  Observatory ──creates job──► Dispatcher ───────► EKS Cluster              │
│       │                           │        │    │    │                     │
│       │                           │        │    │    ▼                     │
│       │                           │        │    │  Job Pod                 │
│       │                           │        │    │    │ reads spec (S3)     │
│       │                           ▼        │    │    │ runs episode        │
│       │                    ┌──────────┐    │    │    │                     │
│       │                    │ S3       │◄───────────(presigned GET/PUT)     │
│       │                    │ policies │    │    │    │                     │
│       │                    │ specs    │    │    │    │                     │
│       │                    │ results  │    │    │    │                     │
│       │                    │ replays  │    │    │    │                     │
│       │                    │ logs     │    │    │    │                     │
│       │                    │ debug    │    │    │    │                     │
│       │                    └────┬─────┘    │    │                          │
│       │                         │          │    │                          │
│       │         watches pods    │          │    │                          │
│       │              │          │          │    │                          │
│       ▼              ▼          ▼          │    └──────────────────────────┘
│  Watcher (reads results, updates Observatory)
│                                            │
└────────────────────────────────────────────┘
```

### Component Responsibilities

**Dispatcher** (primary account, Observatory backend)

- Creates k8s jobs in eval cluster via cross-account EKS API auth
- Resolves metta:// policy URIs to policy S3 keys
- Generates presigned S3 URIs for job spec, results, replay, and policy files
- Job creation path adds `debug_uri` to the job spec
- Writes job spec to the eval artifacts bucket
- No longer passes `MACHINE_TOKEN` to jobs

**single_episode_runner** (eval account, in job pod)

- Reads job spec from presigned GET URL (env var `JOB_SPEC_URI`)
- Downloads policies from presigned GET URLs (policy bucket)
- Runs pure episode runner
- Writes results/replay to presigned PUT URLs (env vars `RESULTS_URI`, `REPLAY_URI`)
- If `debug_uri` is provided in the job spec, a debug.zip can be uploaded (TODO: wire into presigned flow)
- No Observatory access, no AWS credentials

**Watcher** (primary account)

- Watches k8s pod events in eval cluster via cross-account EKS API auth
- On job completion: reads results from S3, updates Observatory and episode metrics
- On job failure: records error reason (OOMKilled, etc.), updates Observatory
- Uploads pod logs to S3 (`jobs/<job_id>/logs.txt`)
- Deletes completed k8s jobs

### Cross-Account Access

**K8s API access** (Dispatcher and Watcher → Eval EKS):

- Primary account assumes `PrimaryAccountEKSAccess` with external ID `tournament-eval-access`
- EKS bearer token generated from a presigned STS `GetCallerIdentity` URL
- Access entry grants `AmazonEKSClusterAdminPolicy` scoped to `jobs` namespace

**S3 access**:

- Policies live in `POLICY_S3_BUCKET` (primary account)
- Job artifacts live in `EVAL_S3_BUCKET` (primary account)
- Dispatcher generates presigned GET URLs for job spec and policy files
- Job creation path generates presigned PUT URLs for results, replay, and debug files
- Job pods have no AWS credentials; all S3 access via presigned URLs
- Watcher reads results directly (no cross-account access needed)

**Container images**:

- CI pushes episode-runner image to both primary and eval ECR
- Eval cluster pulls from eval ECR (no cross-account pull)

### Job Lifecycle

1. **Job Creation** (primary account)
   - Observatory creates job row in Postgres (status=pending)
   - Backend resolves metta:// policy URIs to policy S3 keys, adds `debug_uri`
   - Dispatcher generates presigned S3 URIs for spec/policies/results/replay
   - Dispatcher writes job spec to `EVAL_S3_BUCKET`
   - Dispatcher creates k8s job in eval cluster with env vars: `JOB_SPEC_URI`, `RESULTS_URI`, `REPLAY_URI`
   - Job status → dispatched

2. **Job Execution** (eval account)
   - Pod starts, reads spec from `JOB_SPEC_URI`
   - Downloads policies from presigned URIs
   - Runs episode (no Observatory API access)
   - Writes results to `RESULTS_URI`, replay to `REPLAY_URI`
   - Exits

3. **Event Handling** (primary account)
   - Watcher sees pod phase change
   - On completion: fetches results from S3, writes to Observatory, marks job completed
   - On failure: records error from k8s event, marks job failed
   - Uploads pod logs to S3 for debugging
   - Deletes k8s job

### v1 Simplifications

- Watcher handles event watching, reconciliation, log capture, and result processing (no SQS queue)
- Single eval cluster (`tournament`)

### Future Enhancements

- Split Watcher → Watcher + SQS + Processor (for multi-cluster, decoupled scaling)
- Multi-cluster support (all clusters push to same SQS, single processor)
- Kata containers for process isolation (game runner + policy server split)
- Fargate instead of warm EC2 pool (if job runtime decreases enough)
- Batch stepping across games for GPU utilization (post-launch)

## Open Questions

1. Hot pool sizing strategy?
2. Memory limits for models (100m params × 8 agents)?
