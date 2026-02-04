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

added 5 monitors to `devops/datadog/monitors.py`:

1. **job lifecycle failure rate** - alerts when >10% of jobs fail due to infrastructure issues (pod_not_found,
   pod_deleted, result errors)
2. **oom rate** - alerts when >5% of failures are OOM
3. **high pending queue** - alerts when >50 jobs pending for >10min
4. **slow dispatch** - alerts when p95 dispatch time >2min
5. **no job activity** - alerts when no job transitions for 10min

all include minimum volume guards to prevent false positives on low traffic.
