# Tournament Account Bootstrap

Bootstraps the Tournament AWS account (583928386201) for Spacelift access.

This has already been applied and is here for documentation.

## Output

```
spacelift_role_arn = "arn:aws:iam::583928386201:role/Spacelift"
```

## Re-running (if needed)

```bash
export AWS_PROFILE=tournament
cd devops/tf/tournament-bootstrap
terraform init
terraform plan
terraform apply
```
