output "postgres_endpoint" {
  value = aws_db_instance.postgres.endpoint
}

output "postgres_read_replica_endpoint" {
  value = aws_db_instance.postgres_read_replica.endpoint
}

output "readonly_db_uri_secret_name" {
  value = aws_secretsmanager_secret.readonly_db_uri.name
}

output "readonly_db_username" {
  value = var.readonly_db_username
}

output "postgres_password" {
  value     = random_password.db.result
  sensitive = true
}
