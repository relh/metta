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

# Grant the cross-account role admin access to the EKS cluster (namespace-scoped for jobs)
# and add it to the node-reader group for cluster-scoped node label reads.
resource "aws_eks_access_entry" "primary_account" {
  cluster_name      = module.eks.cluster_name
  principal_arn     = aws_iam_role.primary_account_eks_access.arn
  kubernetes_groups = ["primary-account-node-reader"]
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

# Minimal ClusterRole: only get/list/watch on nodes (cluster-scoped resource).
# This lets the watcher read node labels to capture instance_type/capacity_type
# without granting any broader cluster-wide read (e.g. secrets).
resource "kubernetes_cluster_role" "node_reader" {
  metadata {
    name = "primary-account-node-reader"
  }

  rule {
    api_groups = [""]
    resources  = ["nodes"]
    verbs      = ["get", "list", "watch"]
  }

  depends_on = [aws_eks_access_entry.primary_account]
}

resource "kubernetes_cluster_role_binding" "primary_account_node_reader" {
  metadata {
    name = "primary-account-node-reader"
  }

  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "ClusterRole"
    name      = kubernetes_cluster_role.node_reader.metadata[0].name
  }

  subject {
    kind      = "Group"
    name      = "primary-account-node-reader"
    api_group = "rbac.authorization.k8s.io"
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
