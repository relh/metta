resource "aws_ssoadmin_permission_set" "contractor" {
  name             = "ContractorAccess"
  instance_arn     = var.sso_instance_arn
  session_duration = "PT8H"
}

resource "aws_ssoadmin_permission_set_inline_policy" "contractor" {
  instance_arn       = var.sso_instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.contractor.arn

  inline_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "BedrockInvoke"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream",
          "bedrock:ListFoundationModels",
          "bedrock:ListInferenceProfiles",
        ]
        Resource = "*"
      },
      {
        Sid    = "S3ReadOnly"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket",
          "s3:GetBucketLocation",
        ]
        Resource = "*"
      },
      {
        Sid      = "SSOBasics"
        Effect   = "Allow"
        Action   = ["sts:GetCallerIdentity"]
        Resource = "*"
      },
    ]
  })
}

resource "aws_ssoadmin_account_assignment" "contractor" {
  for_each = var.account_ids

  instance_arn       = var.sso_instance_arn
  permission_set_arn = aws_ssoadmin_permission_set.contractor.arn

  principal_id   = var.contractor_group_id
  principal_type = "GROUP"

  target_id   = each.value
  target_type = "AWS_ACCOUNT"
}
