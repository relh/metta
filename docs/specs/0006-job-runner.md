# Job Runner

> **Status:** Draft **Author:** Rhys, Nishad **Created:** 2026-01-15

## Summary

Define the job runner architecture for executing evaluation jobs with untrusted user-submitted policy code.

## Problem

### Current status

Recently, we moved to a Job running system like so:

- Client submits job request to Observatory Backend
  - Postgres. See current (job params, status, timestamps, results)
  - EKS Cluster → k8s job. Not fargate yet so that it’s easier to test locally
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

## Solution

## Goals

Run tournament evaluation jobs in a dedicated AWS account and k8s cluster separate from the primary infrastructure. Use
a hot pool of pre-warmed pods with possible per-job teardown. Jobs don't submit their own results or pull their inputs
from observatory.

## Non-goals

- Policies may be able to tamper with the integrity of the games in which they're playing, each other, k8s cluster
- Therefore we won't get airtight attribution of which policies eat up too much memory or cause crashes
- There may still be ways for policies to interact with the internet
- We don't yet support running policies as distinct docker images, and don't support submission in that format yet
- This spec is not committing to performance targets (dollars or time per episode)

### Isolation boundary: AWS account

| Component                  | Location        |
| -------------------------- | --------------- |
| Observatory Backend        | Primary account |
| Postgres                   | Primary account |
| Job Watcher                | Primary account |
| Episode Runner pods in VPC | Eval account    |
| K8s cluster                | Eval account    |
| User Policy Code           | Eval account    |

### Hot pool

Pre-warmed nodes + per-job teardown. Each job gets a fresh pod, ~5-10s startup target. Don't want to incur EC2 startup
time per job. We want to ensure that one node runs exactly one pod; right now, it does so by accident, and also doesn't
tear down.

## Job inputs and outputs

In addition to what it's already specifying in its k8s job, observatory gives a presigned s3 uri in its k8s job spec to
each of the policies, and one for results.json and replay file.

This is because the new episode runner shouldn't be able to interact with observatory directly.

## Open Questions

1. Hot pool sizing strategy?
2. Should Watcher be the one to upload episode-job results from output presigned URIs to observatory, or should it spawn
   a k8s job in a different context to do the same (where the job is specified by observatory in the k8s job spec)?
3. Should we have Watcher consume from a queue instead of processing k8s events live?
4. Figure out how much space we need for a 100m subho model and limit to that (for 8 agents all loaded into memory
   together)
5. Any complexity in Observatory or Watcher getting access to Eval account's EKS?
6. How is Eval account getting the image on which to run? Can we set up perms such that it pulls from primary account's
   ECR (or preferably have primary acc push to its ECR)?
7. What are clean ways to manage terraform across multiple AWS accounts?

### Future: process isolation via Kata containers

- Currently policies run in same process as game. Could split into game runner + policy server (user code in Kata
  container, communicates via protobuf-defined interface). There's progress on this already but it's not needed for
  launch.
- Possible that fargate, which automatically handles teardown, would be preferable to keeping a warm ec2 node pool. In
  practice we experienced that it took a few minutes to start up each job. In the current state of things, where jobs
  take ten(s) of minutes, that's not a big deal. But we aim to bring job runtime down.
- One thing that'd likely bring down cost per episode dramatically, at the cost of allowing within-policy gossip across
  agents and episodes, is making use of policies' batch step by asking for actions across many games at once. This would
  also require GPU machines. To consider post-launch.
