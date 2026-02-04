# Episode Runner Alerting

> **Status:** Implemented **Author:** Akshay **Created:** 2026-02-02

## Summary

Add Datadog monitors on existing Observatory metrics to page when episode runners show signs of problems (high failure
rates, resource issues, queue buildup).

## Problem

we have good metrics and dashboards showing episode runner health, but no alerts that page us when things go wrong. when
there's a failure spike or jobs get stuck, we only notice when someone checks the dashboard.

## Solution

add 6 Datadog monitors to `devops/datadog/monitors.py` that alert on existing metrics: job lifecycle failure rates, OOM
rates, queue buildup, slow dispatch, and missing jobs. also track (but don't alert on) execution duration. these
complement existing monitors by adding percentage-based failure rates and detecting when the tournament system stops
creating jobs.

## Goals

get paged when episode runner infrastructure has problems: lifecycle failures, OOM, queue buildup, slow dispatch, or
stopped job creation.

## Monitors

Deployed 6 monitors to production Datadog (critical thresholds only, no warnings to avoid noise):

**Kubernetes (3):**

1. **deployment replicas down** - alerts when replicas unavailable for 10+ min
2. **crashloopbackoff** - alerts when pods stuck in crashloop
3. **too many nodes** - alerts when node count exceeds 200 (cost protection)

**Tournament (3):** 4. **high job failure rate** - alerts when >20 failures in 15 min 5. **job queue buildup** - alerts
when total outstanding jobs >180 (approaching backpressure limit of 200) 6. **high pending queue** - alerts when >100
jobs pending for >10 min

**Not deployed (to avoid false positives):**

- job lifecycle/OOM rate monitors - Datadog API doesn't support compound queries with &&
- slow dispatch monitor - percentile queries don't work on this metric type
- low running jobs - too dependent on tournament schedule
- no job activity - alerts during legitimate downtime
