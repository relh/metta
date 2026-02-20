output "postgres_endpoint" {
  value = aws_db_instance.postgres.endpoint
}

output "postgres_read_replica_endpoint" {
  value = aws_db_instance.postgres_read_replica.endpoint
}

output "dashboard_readonly_db_uri_secret_name" {
  value = aws_secretsmanager_secret.dashboard_readonly_db_uri.name
}

output "postgres_password" {
  value     = random_password.db.result
  sensitive = true
}
