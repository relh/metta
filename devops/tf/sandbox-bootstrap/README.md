# Sandbox Account Bootstrap

Bootstraps the Sandbox AWS account for Spacelift access.

## Applying

```bash
export AWS_PROFILE=sandbox-admin
cd devops/tf/sandbox-bootstrap
terraform init
terraform plan
terraform apply
```
