---
name: do.datadog-api-auth
description:
  Use when Datadog API access is needed (dashboards, monitors, logs) and authentication details are missing or unclear,
  especially when keys may be stored in AWS Secrets Manager.
---

# Datadog API Auth

## Overview

Set up Datadog API authentication quickly and safely, preferring AWS Secrets Manager (`datadog/api-key`,
`datadog/app-key`) over manual key handling.

**Announce at start:** "Setting up Datadog API auth via AWS Secrets Manager and validating access before querying."

## Step 1: Confirm AWS identity and region

```bash
aws sts get-caller-identity --output json
aws configure get region || echo "No default AWS region configured"
```

If AWS auth fails, stop and fix AWS credentials first.

## Step 2: Resolve Datadog auth inputs

```bash
export DD_SITE="${DD_SITE:-datadoghq.com}"
export DD_API_URL="https://api.${DD_SITE}"

export DD_API_KEY="$(aws secretsmanager get-secret-value \
  --secret-id datadog/api-key \
  --query SecretString --output text)"

export DD_APP_KEY="$(aws secretsmanager get-secret-value \
  --secret-id datadog/app-key \
  --query SecretString --output text)"
```

## Step 3: Validate auth and run smoke checks

```bash
curl -fsS "${DD_API_URL}/api/v1/validate" \
  -H "DD-API-KEY: ${DD_API_KEY}"

curl -fsS "${DD_API_URL}/api/v1/dashboard" \
  -H "DD-API-KEY: ${DD_API_KEY}" \
  -H "DD-APPLICATION-KEY: ${DD_APP_KEY}"
```

For safe summaries, parse output and print IDs/titles/counts only. Never print raw keys.

## Step 4: Troubleshoot quickly

1. `AccessDeniedException`: AWS role lacks `secretsmanager:GetSecretValue`.
2. `403` on dashboards: app key missing, invalid, or lacks permissions.
3. `401` on validate: API key invalid or wrong `DD_SITE`.
4. Empty or wrong data: verify region and Datadog site (`datadoghq.com`, `datadoghq.eu`, `us3.datadoghq.com`, etc.).

## Quick Reference

| Need                | Command / Value                    |
| ------------------- | ---------------------------------- |
| API key secret name | `datadog/api-key`                  |
| App key secret name | `datadog/app-key`                  |
| API key validation  | `GET /api/v1/validate`             |
| List dashboards     | `GET /api/v1/dashboard`            |
| Required headers    | `DD-API-KEY`, `DD-APPLICATION-KEY` |
| Base URL            | `https://api.${DD_SITE}`           |

## Integration

**Called by:**

- Any infra/debug skill that needs Datadog dashboard/monitor/log API access.

**Pairs with:**

- `db.run-and-triage` when an operational command fails and Datadog evidence is needed.
