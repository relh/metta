# IAM role that can be assumed by the primary account for EKS access
# Used by the observatory backend to dispatch and watch eval jobs

resource "aws_iam_role" "primary_account_eks_access" {
  name        = "PrimaryAccountEKSAccess"
  description = "Allows primary account to access EKS cluster for job dispatch/watch"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${var.primary_account_id}:root"
        }
        Action = "sts:AssumeRole"
        Condition = {
          StringEquals = {
            "sts:ExternalId" = "tournament-eval-access"
          }
        }
      }
    ]
  })
}

# Policy allowing EKS describe/access
resource "aws_iam_role_policy" "eks_access" {
  name = "EKSAccess"
  role = aws_iam_role.primary_account_eks_access.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "eks:DescribeCluster",
          "eks:ListClusters"
        ]
        Resource = module.eks.cluster_arn
      }
    ]
  })
}

# Grant the cross-account role admin access to the EKS cluster
resource "aws_eks_access_entry" "primary_account" {
  cluster_name  = module.eks.cluster_name
  principal_arn = aws_iam_role.primary_account_eks_access.arn
}

resource "aws_eks_access_policy_association" "primary_account" {
  cluster_name  = module.eks.cluster_name
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
  principal_arn = aws_iam_role.primary_account_eks_access.arn

  access_scope {
    type       = "namespace"
    namespaces = [var.jobs_namespace]
  }
}

# Grant SSO roles direct cluster access for developers
resource "aws_eks_access_entry" "admin" {
  for_each      = toset(local.admins)
  cluster_name  = module.eks.cluster_name
  principal_arn = each.value
}

resource "aws_eks_access_policy_association" "admin" {
  for_each      = toset(local.admins)
  cluster_name  = module.eks.cluster_name
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
  principal_arn = each.value

  access_scope {
    type = "cluster"
  }

  depends_on = [aws_eks_access_entry.admin]
}

# Output the role ARN for use in primary account configuration
output "eks_access_role_arn" {
  value       = aws_iam_role.primary_account_eks_access.arn
  description = "ARN of the role for primary account to assume for EKS access"
}

output "cluster_endpoint" {
  value       = module.eks.cluster_endpoint
  description = "EKS cluster endpoint"
}

output "cluster_name" {
  value       = module.eks.cluster_name
  description = "EKS cluster name"
}
