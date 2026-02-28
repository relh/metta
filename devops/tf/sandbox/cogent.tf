# Cogent agent instance — IAM, instance profile, security group.
# The EC2 instance itself is launched manually (see devops/cogent/README.md).

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

resource "aws_security_group" "cogent" {
  name        = "cogent-sg"
  description = "Cogent agent instance - egress only, SSM access (no inbound)"

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
