---
name: n.create-aws-account
description: |
  Set up a new AWS account under the Softmax organization with Spacelift, SSO profiles, and baseline infrastructure.
---

# Create a New AWS Account

## Prerequisites

- AWS Organizations access (management account)
- Spacelift admin at https://metta-ai.app.spacelift.io/
- AWS SSO access at https://softmaxx.awsapps.com/start/

## Steps

### 1. Create the Account in AWS Organizations (manual)

In the AWS Organizations console (management account), create a new account. Note the **account ID**.

### 2. Enable SSO Access (manual)

In AWS IAM Identity Center (SSO), assign the appropriate permission sets (PowerUserAccess, AdministratorAccess) to
users/groups for the new account. This makes the account accessible via `https://softmaxx.awsapps.com/start/`.

### 3. Add AWS CLI Profiles

**Do this before the bootstrap step** -- terraform needs a valid AWS profile to authenticate.

Update `devops/aws/setup_aws_profiles.sh` in the `initialize_aws_config` function:

```bash
aws configure set profile.<account>.sso_session softmax-sso
aws configure set profile.<account>.sso_account_id <ACCOUNT_ID>
aws configure set profile.<account>.sso_role_name PowerUserAccess
aws configure set profile.<account>.region us-east-1

aws configure set profile.<account>-admin.sso_session softmax-sso
aws configure set profile.<account>-admin.sso_account_id <ACCOUNT_ID>
aws configure set profile.<account>-admin.sso_role_name AdministratorAccess
aws configure set profile.<account>-admin.region us-east-1
```

Then run the script (or `aws sso login`) to populate the local config.

### 4. Bootstrap Spacelift Role

Create `devops/tf/<account>-bootstrap/` by copying from `devops/tf/tournament-bootstrap/`:

```
devops/tf/<account>-bootstrap/
├── providers.tf          # AWS provider, region, default tags (update Stack tag)
├── spacelift-role.tf     # IAM role trusting Spacelift's AWS account (324880187172)
├── variables.tf          # spacelift_aws_account_id, spacelift_account_name (Metta-AI)
├── README.md
└── .gitignore
```

Apply manually (one-time, before Spacelift can manage the account):

```bash
export AWS_PROFILE=<account>-admin
cd devops/tf/<account>-bootstrap
terraform init
terraform plan
terraform apply
```

Output: `arn:aws:iam::<ACCOUNT_ID>:role/Spacelift`

### 5. Register Spacelift Integration

Add a `spacelift_aws_integration` resource in `devops/tf/spacelift/aws.tf`:

```hcl
resource "spacelift_aws_integration" "<account>" {
  name               = "<account>-aws"
  role_arn           = "arn:aws:iam::<ACCOUNT_ID>:role/Spacelift"
  duration_seconds   = 3600
  autoattach_enabled = true
  labels             = ["autoattach:<account>-aws"]
}
```

Push to a PR and apply via Spacelift (the `spacelift` stack).

### 6. Create Spacelift Stack (manual)

In the Spacelift UI (https://metta-ai.app.spacelift.io/):

1. Create a new stack pointing to `devops/tf/<account>/`
2. Use latest OpenTofu
3. Optionally enable Local Preview and Autodeploy
4. **Do NOT attach the cloud integration yet** -- it doesn't exist until step 5 is applied

### Ordering: merge and attach integration

Steps 5 and 7 can be in the same PR. On merge:

1. The `spacelift` stack auto-applies, creating the `<account>-aws` integration
2. Go to the `<account>` stack > Settings > Integrations > attach `<account>-aws`
3. Trigger a run on the `<account>` stack -- it will now have AWS credentials and can plan/apply

**If the stack plans before you attach the integration**, it will fail with "No valid credential sources found". This is
expected -- just attach the integration and re-trigger.

### 7. Create Terraform Stack

Create `devops/tf/<account>/` with the infrastructure needed. Common resources:

| Resource                   | When needed                                                                     |
| -------------------------- | ------------------------------------------------------------------------------- |
| VPC + subnets              | Almost always (use a unique CIDR like `10.N.0.0/16`)                            |
| EKS cluster                | If running k8s workloads                                                        |
| ECR repos                  | If building/pushing container images                                            |
| S3 buckets                 | If storing artifacts                                                            |
| IAM roles                  | For service workloads                                                           |
| SkyPilot IAM (user + role) | If launching EC2 instances via SkyPilot (copy from `devops/tf/skypilot/iam.tf`) |

All `.tf` files should tag resources with `Stack = "<account>"`.

### 8. Cross-Account Access (if needed)

If the primary account needs to reach into this account (like tournament):

- **This account:** Create an IAM role with a trust policy allowing the primary account to assume it (see
  `devops/tf/tournament/cross-account.tf`)
- **Primary account:** Add assume-role permissions to the relevant IRSA roles (see `devops/tf/eks/observatory.tf`)

If this account needs to reach primary account resources:

- Use presigned URLs (no IAM needed) or create cross-account trust policies

### 9. kubectl Context (if EKS)

```bash
aws eks update-kubeconfig --name <cluster> --region us-east-1 --profile <account> --alias <account>
```

## Reference

| Account           | ID           | Terraform                                     | Spacelift label             |
| ----------------- | ------------ | --------------------------------------------- | --------------------------- |
| Primary (Softmax) | 751442549699 | `devops/tf/eks/`, `devops/tf/skypilot/`, etc. | `autoattach:aws`            |
| Tournament        | 583928386201 | `devops/tf/tournament/`                       | `autoattach:tournament-aws` |
| Sandbox           | 015142856185 | `devops/tf/sandbox/`                          | `autoattach:sandbox-aws`    |

## Key Files

- `devops/tf/spacelift/aws.tf` - Spacelift AWS integrations
- `devops/tf/sandbox-bootstrap/` - Reference bootstrap stack (simplest example)
- `devops/tf/sandbox/` - Reference account infrastructure (SkyPilot IAM only)
- `devops/tf/tournament/` - Reference for cross-account access and EKS setup
- `devops/aws/setup_aws_profiles.sh` - AWS CLI profile setup

## Worked Example

Commit `7901cb0349` (#7237) added the Sandbox account end-to-end. Use `git show 7901cb0349` to see the minimal diff
covering all steps.
