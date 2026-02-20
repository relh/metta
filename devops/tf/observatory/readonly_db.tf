# Intentionally managed outside Terraform for now.
#
# 2026-02-20: The Spacelift worker applying this stack cannot reach private RDS
# on port 5432, so role/grant management via the postgresql provider times out.
# The `readonly` role + grants are provisioned manually until worker networking is
# fixed, then this file can be restored to Terraform-managed resources.
