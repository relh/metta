# Tournament Account Infrastructure

This stack provisions the infrastructure in the tournament AWS account (583928386201).

## Purpose

Per [Job Runner Spec](/docs/specs/0006-job-runner.md), evaluation jobs run in a dedicated AWS account separate from
primary infrastructure. This provides isolation for untrusted user-submitted code.

## Components

- **EKS Cluster**: Runs evaluation job pods using EKS auto mode for node scaling
- **VPC**: Network infrastructure for the cluster
- **ECR**: Container registry for episode-runner images (CI pushes to both accounts)
- **Cross-Account IAM**: Role for primary account's Dispatcher/Watcher to access EKS

## Cross-Account Access

The primary account (751442549699) accesses this cluster via:

1. **IAM Role**: `PrimaryAccountEKSAccess` can be assumed by primary account
2. **EKS Access Entry**: Role has admin access scoped to `jobs` namespace

Dispatcher and Watcher use this pattern:

```bash
aws sts assume-role \
  --role-arn arn:aws:iam::583928386201:role/PrimaryAccountEKSAccess \
  --external-id tournament-eval-access
```

Then use those credentials with `aws eks get-token --cluster-name tournament`.

## Spacelift

This stack uses the `tournament-aws` integration via autoattach.

When creating the stack:

- Add label: `autoattach:tournament-aws`
- Project Root: `devops/tf/tournament`

## Outputs

After applying:

- `eks_access_role_arn`: Role ARN for primary account config
- `cluster_endpoint`: EKS API endpoint
- `cluster_name`: Cluster name for kubeconfig
- `ecr_repository_url`: ECR URL for CI to push images
