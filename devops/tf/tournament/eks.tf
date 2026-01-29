locals {
  vpc_cidr = "10.1.0.0/16"
  azs      = slice(data.aws_availability_zones.available.names, 0, 3)

  tags = {
    Terraform = "true"
    Stack     = "tournament"
  }

  # Add new roles here to grant them access to the EKS cluster.
  admins = [
    "arn:aws:iam::583928386201:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_AdministratorAccess_ff47d45445c4a87a",
    "arn:aws:iam::583928386201:role/aws-reserved/sso.amazonaws.com/AWSReservedSSO_PowerUserAccess_5be0f4f1939ddd98",
  ]
}

data "aws_availability_zones" "available" {
  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.31"

  cluster_name                   = var.cluster_name
  cluster_version                = var.cluster_version
  cluster_endpoint_public_access = true

  enable_cluster_creator_admin_permissions = true

  # EKS auto mode for automatic node scaling
  cluster_compute_config = {
    enabled    = true
    node_pools = ["general-purpose"]
  }

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  tags = local.tags
}

data "aws_eks_cluster" "tournament" {
  name = var.cluster_name
}

resource "aws_security_group_rule" "kubelet_logs_from_control_plane" {
  description              = "Allow EKS control plane to read kubelet logs"
  type                     = "ingress"
  protocol                 = "tcp"
  from_port                = 10250
  to_port                  = 10250
  security_group_id        = module.eks.node_security_group_id
  source_security_group_id = data.aws_eks_cluster.tournament.vpc_config[0].cluster_security_group_id
}

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = var.cluster_name
  cidr = local.vpc_cidr

  azs             = local.azs
  private_subnets = [for k, v in local.azs : cidrsubnet(local.vpc_cidr, 4, k)]
  public_subnets  = [for k, v in local.azs : cidrsubnet(local.vpc_cidr, 8, k + 48)]

  enable_nat_gateway = true
  single_nat_gateway = true

  public_subnet_tags = {
    "kubernetes.io/role/elb" = 1
  }

  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = 1
  }

  tags = local.tags
}

# Resources removed from Terraform management but kept in cluster
# (managed via helmfile-tournament.yaml instead)
removed {
  from = helm_release.system
  lifecycle {
    destroy = false
  }
}

removed {
  from = kubernetes_namespace.jobs
  lifecycle {
    destroy = false
  }
}

removed {
  from = kubernetes_service_account.episode_runner
  lifecycle {
    destroy = false
  }
}
