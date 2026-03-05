---
name: do.fix-alembic-startup-crash-move-migrations-pre-deploy-helm
description: 'Use when fixing alembic startup crash move migrations pre deploy helm.'
---

# Fix Alembic Startup Crash Move Migrations Pre Deploy Helm

## Trigger

- Primary: "fixing alembic startup crash move migrations pre deploy helm"

## Workflow

- Reproduce startup failure in the deployment path and confirm whether Alembic migrations run before app boot.
- Fix migration ordering in Helm/pre-deploy hooks so schema changes are applied before dependent services start.
- Validate migration idempotency and rollback behavior on a non-prod environment.
- Summarize root cause, deployment sequencing changes, and any operator follow-up steps.
