locals {
  iam_role_name = "Spacelift"
}

resource "aws_iam_role" "spacelift" {
  name        = local.iam_role_name
  description = "Role allowing Spacelift to deploy to AWS. Created by Terraform."

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${var.spacelift_aws_account_id}:root"
        }
        Action = "sts:AssumeRole"
        Condition = {
          StringLike = {
            "sts:ExternalId" = "${var.spacelift_account_name}@*"
          }
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "spacelift_poweruser" {
  policy_arn = "arn:aws:iam::aws:policy/PowerUserAccess"
  role       = aws_iam_role.spacelift.name
}

resource "aws_iam_role_policy_attachment" "spacelift_iam" {
  policy_arn = "arn:aws:iam::aws:policy/IAMFullAccess"
  role       = aws_iam_role.spacelift.name
}

output "spacelift_role_arn" {
  value       = aws_iam_role.spacelift.arn
  description = "ARN of the Spacelift role - use this when registering the integration"
}
