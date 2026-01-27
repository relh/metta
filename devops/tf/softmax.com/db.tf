resource "random_password" "db" {
  length  = 32
  special = false
}

# Security group and DB subnet group for accessing the DB from the EKS cluster
# Created by observatory stack (TODO: move this somewhere else)
data "aws_security_group" "db" {
  name = "${var.eks_cluster_name}-postgres-sg"
}

data "aws_db_subnet_group" "db" {
  name = "${var.eks_cluster_name}-db"
}


resource "aws_db_instance" "postgres" {
  identifier     = "softmax-com-pg"
  engine         = "postgres"
  engine_version = var.db_postgres_version

  instance_class    = var.db_instance_class
  allocated_storage = var.db_allocated_storage
  multi_az          = true

  db_subnet_group_name   = data.aws_db_subnet_group.db.name
  vpc_security_group_ids = [data.aws_security_group.db.id]
  publicly_accessible    = false # stays inside the VPC

  backup_retention_period = 7

  db_name  = "softmax_com"
  username = "softmax_com"
  password = random_password.db.result

  skip_final_snapshot = true
}

locals {
  postgres_url = "postgresql://${aws_db_instance.postgres.username}:${random_password.db.result}@${aws_db_instance.postgres.endpoint}/${aws_db_instance.postgres.db_name}"
}
