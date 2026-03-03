# Cogent agent instance — IAM, instance profile, security group.
# The EC2 instance itself is launched manually (see devops/cogent/README.md).

# These resources were created manually before being codified in Terraform.
# Import blocks adopt them into TF state on first apply, then become no-ops.
# After successful import, these blocks can be removed in a follow-up.

import {
  to = aws_iam_role.cogent
  id = "cogent-role"
}

import {
  to = aws_iam_instance_profile.cogent
  id = "cogent-profile"
}

import {
  to = aws_iam_role_policy.cogent_secrets
  id = "cogent-role:cogent-secrets"
}

import {
  to = aws_iam_role_policy.cogent_bedrock
  id = "cogent-role:bedrock-claude-code"
}

import {
  to = aws_iam_role_policy_attachment.cogent_ssm
  id = "cogent-role/arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

import {
  to = aws_security_group.cogent
  id = "sg-04dcd1e41a6fc023b"
}

resource "aws_iam_role" "cogent" {
  name = "cogent-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_instance_profile" "cogent" {
  name = "cogent-profile"
  role = aws_iam_role.cogent.name
}

resource "aws_iam_role_policy" "cogent_secrets" {
  name = "cogent-secrets"
  role = aws_iam_role.cogent.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
      Resource = "arn:aws:secretsmanager:us-east-1:${local.account_id}:secret:*"
    }]
  })
}

resource "aws_iam_role_policy" "cogent_bedrock" {
  name = "bedrock-claude-code"
  role = aws_iam_role.cogent.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "BedrockClaudeCode"
      Effect = "Allow"
      Action = [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
        "bedrock:ListInferenceProfiles",
      ]
      Resource = [
        "arn:aws:bedrock:*:*:inference-profile/*",
        "arn:aws:bedrock:*:*:application-inference-profile/*",
        "arn:aws:bedrock:*:*:foundation-model/*",
      ]
    }]
  })
}

resource "aws_iam_role_policy_attachment" "cogent_ssm" {
  role       = aws_iam_role.cogent.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_vpc" "default" {
  default = true
}

resource "aws_security_group" "cogent" {
  name        = "cogent-sg"
  description = "Cogent agent instance - egress only, SSM access (no inbound)"
  vpc_id      = data.aws_vpc.default.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
