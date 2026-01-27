# Tournament AWS Account

> **Status:** Implemented **Author:** Nishad **Created:** 2026-01-26

## Summary

Dedicated AWS account (583928386201) for running tournament evaluation jobs, isolated from primary infrastructure
(751442549699). See [0006-job-runner](./0006-job-runner.md) for the job lifecycle this supports.

## Problem

Evaluation jobs execute untrusted user-submitted policy code. Running these in the primary account puts all
infrastructure at risk. A separate account provides a hard boundary: compromised jobs cannot reach production databases,
services, or credentials.

## Design

### Accounts

| Account    | ID           | Purpose                                        |
| ---------- | ------------ | ---------------------------------------------- |
| Primary    | 751442549699 | Observatory, dispatcher, watcher, S3, Postgres |
| Tournament | 583928386201 | EKS cluster for job execution, ECR for images  |

### Cross-Account Permissions

Three interactions cross the account boundary:

#### 1. Observatory backend -> Tournament EKS (dispatch and watch jobs)

```
Observatory pod (primary EKS)
  -> IRSA role: observatory-backend
  -> sts:AssumeRole (ExternalId: "tournament-eval-access")
  -> PrimaryAccountEKSAccess role (tournament account)
  -> EKS access: AmazonEKSClusterAdminPolicy scoped to "jobs" namespace
```

Terraform: `eks/observatory.tf` (IRSA + assume permission), `tournament/cross-account.tf` (trust policy + EKS access
entry).

#### 2. CI -> Tournament ECR (push images)

```
GitHub Actions (primary account AWS_ROLE)
  -> amazon-ecr-login with registries: "583928386201"
  -> ECR repo policy allows primary account push/pull
```

CI pulls the commit-pinned image from primary ECR and retags it into tournament ECR. The eval cluster pulls from its own
account's ECR (no cross-account pull at runtime).

Terraform: `tournament/ecr.tf` (repo + cross-account policy).

#### 3. Job pods -> Primary S3 (presigned URLs)

Job pods have no AWS credentials. The dispatcher generates presigned S3 URLs for spec, policy, result, and replay files.
Pods use these URLs directly. No IAM role or cross-account trust needed.

### Tournament Account Resources

| Resource        | Config                                                                |
| --------------- | --------------------------------------------------------------------- |
| EKS cluster     | `tournament`, auto mode, `general-purpose` node pool, public endpoint |
| VPC             | `10.1.0.0/16`, 3 AZs, single NAT gateway                              |
| Namespace       | `jobs`                                                                |
| Service account | `episode-runner` (no IRSA, pods use presigned URLs)                   |
| ECR             | `episode-runner`, mutable tags, 30-image lifecycle                    |
| IAM role        | `PrimaryAccountEKSAccess` (trust: primary account with external ID)   |
| Spacelift       | `Spacelift` role for IaC management                                   |

### Terraform Stacks

| Stack                  | Path                              | Account                                                    |
| ---------------------- | --------------------------------- | ---------------------------------------------------------- |
| `tournament-bootstrap` | `devops/tf/tournament-bootstrap/` | Tournament (bootstraps Spacelift role)                     |
| `tournament`           | `devops/tf/tournament/`           | Tournament (EKS, ECR, cross-account role)                  |
| `eks`                  | `devops/tf/eks/`                  | Primary (includes observatory IRSA with assume permission) |
| `spacelift`            | `devops/tf/spacelift/`            | Primary (registers tournament AWS integration)             |
