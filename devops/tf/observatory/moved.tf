moved {
  from = aws_secretsmanager_secret.dashboard_readonly_db_uri
  to   = aws_secretsmanager_secret.readonly_db_uri
}
