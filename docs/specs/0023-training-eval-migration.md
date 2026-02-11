# Migrate Training Evals from Eval Tasks to Job Requests

> **Status:** Draft **Author:** Nishad, Claude-assisted **Created:** 2025-02-11

## Summary

Replace the eval-task infrastructure (EvalTask, EvalTaskOrchestrator, EvalTaskWorker) with the job-request system
(JobRequest, Dispatcher, Watcher) for running remote training evaluations. Introduces a `TrainingEvalRequest` entity
that coordinates image building, episode job dispatch, result aggregation, and wandb push — with bookkeeping done in a
separate post-processing job rather than inside the watcher.

## Problem

Training uses a bespoke eval-task pipeline for remote evaluation:

1. `Evaluator` creates an `EvalTask` containing a shell command, a serialized simulation list, and a git hash.
2. `EvalTaskOrchestrator` spins up a container, clones the repo at that hash, runs `uv install`, and executes the
   command.
3. The worker runs N simulations in a single fat container, then pushes results to both Observatory and wandb.

This system duplicates functionality that the job-request pipeline already provides (K8s job scheduling, pod monitoring,
result recording) and has several problems:

- **Slow cold start.** Every eval task clones the repo and installs dependencies from scratch.
- **Fragile.** Git checkout + dependency install inside a container fails in ways that are hard to debug.
- **Monolithic.** One container runs all simulations — no parallelism across episodes, no partial results on failure.
- **Separate infrastructure.** The orchestrator and worker are entirely separate from the Dispatcher/Watcher that
  already handle episode jobs for tournaments.

The job-request system is better: pre-built images, one episode per pod, K8s-native scheduling, and event-driven result
recording. But it currently lacks three things that training evals need:

1. An episode-runner image built from the training job's commit (not just from cogames releases).
2. Aggregated wandb push after all episodes complete.
3. Dispatch to the main AWS account (not just the tournament account).

## Solution

Introduce a `TrainingEvalRequest` that orchestrates the full lifecycle:

```
Trainer submits TrainingEvalRequest
    → Backend ensures image exists for git_hash (build if needed)
        → Decompose simulations into individual episode jobs
            → Dispatch as JobRequests to training-evals namespace (main account)
                → Watcher records per-episode results (existing behavior)
                    → Completion trigger spawns aggregator job
                        → Aggregator reads results, pushes to wandb, marks request complete
```

The trainer's interface stays fire-and-forget: call `stats_client.create_training_eval_request(...)` and the backend
handles everything else.

## Goals

- [ ] Training evals run as job_requests (one episode per K8s job) instead of eval tasks
- [ ] Episode runner image is built per commit and cached in ECR
- [ ] Aggregated eval metrics are pushed to wandb with the same format as today
- [ ] Jobs run in a `training-evals` namespace in the main AWS account
- [ ] All eval-task infrastructure is deleted (models, orchestrator, worker, recipe)

## Non-Goals

- Changing how local evaluation works (Evaluator with `evaluate_local=True` is unchanged)
- Changing the tournament job-request pipeline
- Modifying the episode runner's core execution logic (mettagrid.runner)
- Building a general-purpose workflow engine

## Design

### Data Model

New table `training_eval_request`:

```
TrainingEvalRequest:
    id: UUID (PK)
    policy_version_id: UUID
    wandb_run_path: str | None          # "entity/project/run_id"
    epoch: int
    agent_step: int
    git_hash: str
    image_tag: str | None               # set once image is confirmed
    simulations: JSONB                   # list[SimulationRunConfig]
    status: str                         # see state machine below
    created_at: datetime
    completed_at: datetime | None
```

Junction table `training_eval_request_job`:

```
TrainingEvalRequestJob:
    training_eval_request_id: UUID (FK)
    job_request_id: UUID (FK)
```

Status state machine:

```
building_image → dispatching → running → aggregating → completed
      ↓              ↓           ↓            ↓
    failed         failed      failed       failed
```

### Image Pipeline

Extend CI with a new workflow `build-training-eval-image.yml`:

- Triggered via `repository_dispatch` (called by Observatory backend) or `workflow_dispatch` (manual).
- Accepts `git_hash` as input.
- Builds from `Dockerfile.episode_runner` but installs the `metta` package from the repo at that commit (the standard
  episode runner only installs cogames from PyPI).
- Tags as `training-eval-runner:{git_hash}`, pushes to ECR.
- The `TrainingEvalProcessor` checks ECR before triggering a build — same commit reuses the cached image.

Later optimization: pre-build on every push to main so most training runs (which are on main) never wait for a build.

### Multi-Cluster Dispatch

Add a `cluster` column to the `k8s_events` table (or use the existing one if present) to distinguish events from
different clusters. The watcher already processes K8s events in the DB separately from logging them, so this is a
natural extension.

Changes needed:

- Add main-account cluster config to the dispatcher (EKS endpoint, namespace `training-evals`, credentials).
- `JobRequest` gets a `cluster` field (default: `"tournament"`, training evals use `"main"`).
- `get_k8s_client()` routes to the appropriate cluster based on this field.
- Watcher runs watch loops for both clusters, tagging events with the cluster name.

### TrainingEvalProcessor

A backend service (or periodic task) that handles `TrainingEvalRequest` lifecycle:

1. **Image check**: Query ECR for `training-eval-runner:{git_hash}`.
   - If cached, proceed.
   - If missing, trigger GitHub Actions build via API, poll for completion, update `image_tag`.
2. **Decompose simulations**: Convert `SimulationRunConfig` list into `SingleEpisodeJob` specs (one per episode).
3. **Dispatch**: Create `JobRequest` records via the existing batch-creation path, with `cluster="main"`.
4. **Link**: Create `TrainingEvalRequestJob` junction records.
5. **Update status**: `dispatching` → `running`.

### Aggregator Job (Completion Trigger)

When the watcher records a terminal status for a job that belongs to a `TrainingEvalRequest`:

1. Check if all jobs for that request are terminal.
2. If yes, atomically transition the request status from `running` → `aggregating` using a compare-and-set update
   (`UPDATE ... SET status = 'aggregating' WHERE id = ? AND status = 'running' RETURNING id`). If the CAS fails (another
   watcher instance already claimed it), skip — the aggregator is already being handled.
3. Only if the CAS succeeds, spawn a lightweight **aggregator K8s Job** (not inline in the watcher). Track the
   aggregator as a `JobRequest` linked to the parent `TrainingEvalRequest`.
4. The aggregator job:
   - Reads the `TrainingEvalRequest` (simulations config, wandb_run_path, epoch, agent_step).
   - Queries episode results from Observatory for all completed jobs in this request.
   - Aggregates into `EvalResults` (category scores, simulation scores, replay URLs) — same data shape as
     `send_eval_results_to_wandb()`.
   - Pushes to wandb via `WandbRunAppendContext`.
   - Marks the request `completed` (or `failed` if too many episodes failed).

The watcher monitors the aggregator job like any other `JobRequest`. If the aggregator fails or exceeds a configurable
timeout, the watcher marks the `TrainingEvalRequest` as `failed`. This prevents requests from getting stuck in the
`aggregating` state.

The aggregator is a separate job, not watcher logic, because:

- It's a one-shot operation, not continuous monitoring.
- If it fails, it can be retried independently.
- It keeps the watcher focused on pod lifecycle monitoring.

### Client Changes

In `metta/rl/training/evaluator.py`, replace:

```python
evaluate_remotely(
    policy_version_id=policy_version_id,
    simulations=sim_run_configs,
    stats_client=self._stats_client,
    git_hash=self._git_hash,
    push_metrics_to_wandb=...,
)
```

With:

```python
self._stats_client.create_training_eval_request(
    policy_version_id=policy_version_id,
    simulations=[s.model_dump(mode="json") for s in sim_run_configs],
    git_hash=self._git_hash,
    wandb_run_path=self._wandb_run.path if self._wandb_run else None,
    epoch=epoch,
    agent_step=agent_step,
)
```

### What Gets Deleted

Once the migration is validated in production:

| File                                           | What                                     |
| ---------------------------------------------- | ---------------------------------------- |
| `app_backend/.../models/eval_task.py`          | EvalTask, TaskAttempt models             |
| `app_backend/.../queries/eval_task_queries.py` | Query layer, EvalTaskRow                 |
| `app_backend/.../routes/eval_task_routes.py`   | API routes                               |
| `app_backend/.../clients/eval_task_client.py`  | Client                                   |
| `app_backend/.../eval_task_orchestrator.py`    | Container scheduling                     |
| `app_backend/.../eval_task_worker.py`          | Repo clone + eval execution              |
| `recipes/experiment/remote_eval.py`            | Eval recipe run by workers               |
| `metta/sim/remote.py`                          | `evaluate_remotely()` + `SimulationList` |
| DB tables: `eval_task`, `task_attempt`         |                                          |

### Implementation Phases

**Phase 0 — Foundation (parallel tracks, no behavior change):**

- Add `TrainingEvalRequest` model, migration, API endpoints, StatsClient method.
- Create `training-eval-runner` Dockerfile variant.
- Add `build-training-eval-image.yml` GitHub Actions workflow.

**Phase 1 — Multi-cluster support:**

- Add `cluster` field to `JobRequest` and `k8s_events`.
- Configure dispatcher for main-account EKS cluster + `training-evals` namespace.
- Extend watcher to watch both clusters.

**Phase 2 — TrainingEvalProcessor:**

- Implement image-check/build-trigger logic.
- Implement simulation → SingleEpisodeJob decomposition.
- Wire up job dispatch and junction tracking.

**Phase 3 — Aggregator:**

- Implement completion detection in watcher (trigger only, no business logic).
- Build aggregator job: result query, aggregation, wandb push.

**Phase 4 — Client migration:**

- Update `Evaluator.evaluate()` to use `create_training_eval_request()`.
- End-to-end testing: training → request → image build → jobs → aggregation → wandb.
- Run both systems in parallel for validation.

**Phase 5 — Cleanup:**

- Delete eval-task infrastructure (models, orchestrator, worker, routes, recipe, client code).
- DB migration to drop `eval_task` and `task_attempt` tables.

## Other topics

1. **Image build latency.** First eval for a new commit blocks on a Docker build (~2-5 min). That is acceptable.
2. **Partial failure policy.** If 3 out of 20 episode jobs fail, aggregator should report partial results to wandb
3. **Aggregator image.** Aggregator should reuse the `training-eval-runner:{git_hash}` image
4. **No need for a graceful migration.** Just hard cut-over to this new system from the eval-tasks one
