terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.0"
    }
    postgresql = {
      source  = "cyrilgdn/postgresql"
      version = "~> 1.26"
    }
  }
}

provider "aws" {
  region = var.region
}

locals {
  cluster_name = "main"
}

data "aws_eks_cluster" "main" {
  name = local.cluster_name
}

provider "kubernetes" {
  host                   = data.aws_eks_cluster.main.endpoint
  cluster_ca_certificate = base64decode(data.aws_eks_cluster.main.certificate_authority[0].data)
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args        = ["eks", "get-token", "--cluster-name", local.cluster_name]
  }
}

provider "postgresql" {
  host     = aws_db_instance.postgres.address
  port     = aws_db_instance.postgres.port
  database = aws_db_instance.postgres.db_name
  username = aws_db_instance.postgres.username
  password = aws_db_instance.postgres.password
  sslmode  = "require"
}
