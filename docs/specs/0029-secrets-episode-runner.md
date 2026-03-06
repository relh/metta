# Policy Submission Secrets (Phase 1)

**Status:** Draft | **Owner:** Backend + Runner

## Problem

Policy credentials (e.g. `ANTHROPIC_API_KEY`) have no safe path into remote policy execution. Global env injection risks
cross-policy leakage when multiple policies share a runner.

## Solution

Submit-time secrets, stored in Secrets Manager, resolved at dispatch into an S3 bundle (SSE-KMS encrypted), read by the
runner via its existing `read(uri)` path, and injected only into the target policy subprocess via explicit
`Popen(..., env=child_env)`.

## Non-Goals

Strong process isolation (phase 2), secret rotation UX, container hardening.

## Data Flow

1. **Submit** -- CLI sends `policy_secret_env`. Backend creates policy version, then writes `dict[str, str]` to AWS
   Secrets Manager keyed as `cogames/policy-secrets/<policy_version_id>`.
2. **Dispatch** -- Dispatcher reads per-policy secrets from Secrets Manager, assembles a job-scoped bundle, writes it to
   S3 with SSE-KMS (`s3://cogames-secrets/<job_id>/bundle.json`), generates a presigned GET URL with short TTL (e.g. 5
   min), and sets that URL as `POLICY_SECRETS_URI` in runner env.
3. **Run** -- Executor calls `read(POLICY_SECRETS_URI)` on a plain HTTPS URL, parses the bundle, and threads per-policy
   env overrides into policy server launch.

The runner needs no S3, KMS, or Secrets Manager permissions for secrets. The presigned URL is usable only within its TTL
window. The dispatcher deletes the S3 object in job cleanup.

## Security Note

Scopes secrets to subprocess boundaries. Does **not** fully defend against malicious co-located processes. For that we'd
want separate nodes or at least separate containers

## Open Questions

- Should secrets namespace be per-submitter or per-policy upload?
- Should submitters be able to update secrets in-place? If so should secrets have versions? Else jobs may not be easily
  reproducible
