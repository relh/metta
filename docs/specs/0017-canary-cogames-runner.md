# Canary - The Cogames E2E Runner (DEPRECATED)

> [!NOTE] Canary runner has been sunsetted in favor of `devops/stable/function_checks/cogames_submission.py`

A daily job, with a workflow setup similar to `stable-release.yml`.

## High Level Overview

- Downloading `cogames` from PyPi
- Pre-generated _good [(0)](#ref-0)_ policy from `./devops/canary/policies`
- Pre-generated _bad [(3)](#ref-3)_ policy from `./devops/canary/policies`
- Upload the policies with `cogames upload` [(1)](#ref-1)
- Ensure the bad policy does not pass local validation
- Submit the policies to _test-season [(2)](#ref-2)_, with `cogames submit`, using `--skip-validation` on the bad
  policy.
- Validate the submission progress
  - Ensure existence with both `cogames submissions --season=test-season` and `cogames submissions <policy>`
  - Start a poll to the Observatory API's `/job/<id>` that checks status of job
  - Ensure that the bad policy at some stage reports that it has not qualified (error state)
  - Ensure that the good policy at some stage reports that it was successful
  - On completion, check the `cogames leaderboard --season=test-season` result and ensure the good policy exists
- For each step, collect metrics and/or errors
- Write metrics to a well-formatted Discord message
- Send the results to a specified Discord channel (`canary-runs` ?)

## Constraints

The goal is to emulate as much as possible what the actual flow would be for a `cogames` user. Therefor we should
ensure:

- A minimal running environment like `python:3.12.11-slim` with a 'minimal' _Environment Setup_ step.
- Validate as many results as possible using only the `cogames` CLI that requires API requests to the Observatory API.
- Must complete the check within 20 minutes.
- Collect and report only what is useful:
  - Running time.
  - Error messages at any step.
  - Per-command success/error status, running time.

## Technical Specification

A slim `Dockerfile.canary_runner` setup whose Python interpreter is used to run a script in `./devops/canary/cli.py`.
The script is an entrypoint to a `Canary -> run` method which runs the steps outlined in the
[high level overview](#high-level-overview).

### Pre-requisites

- Ensure `test-season` is created and excluded from Observatory's queries.

- Pre-baked good and bad policies which can be generated with `cogames tutorial make-policy`.

- `devops/stable/*` already has dependency-aware parallel execution, Datadog metrics, Discord notifications and job
  status tracking baked in. Extract into new, reusable interfaces in `devops/runners` folder. This constitutes a small
  rewrite of the `stable` and `skypilot` scripts to also make use of these instead.

#### File Structure

```
devops/runners/
  core.py           # Job, Runner (dependency graph, parallel exec)
  executors/
    local.py        # subprocess (exists)
    skypilot.py     # SkyPilot polling (exists)
    observatory.py  # HTTP polling for Observatory (new)
  reporters/
    discord.py      # _write_summary (exists)
    datadog.py      # jobs_to_metrics (exists)
```

#### Components

The `devops/canary/cli.py` is responsible for handling:

- Job definitions of each `cogames` command.
- Parallel execution and result collection + verification of good and bad policy workflows via new
  `./devops/runners/core.py` and local executor.
- Summary generation/concatenation at each step for end-of-work reporting.
- HTTP Polling of Observatory endpoint via `./devops/runners/observatory.py` for status, with a timeout that is shorter
  than overall workflow run to ensure it gets reported if timed out.
- Intrinsic Datadog metric collection.
- End-of-work reporting to Discord via `./devops/runners/reporters/discord.py`.

## Footnotes

<a name="ref-0"></a> (0) -> A policy which does not error, does not necessarily have to perform well.

<a name="ref-1"></a> (1) -> Requires login, without interaction (e.g. browser actions) like with a machine token.

<a name="ref-2"></a> (2) -> This season should be created, and changes to Observatory should be made to hide this season
from the queries.

<a name="ref-3"></a> (3) -> A policy that will fail local validation, but that we'll submit anyway with
`--skip-validation`.
