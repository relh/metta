moved {
  from = aws_secretsmanager_secret.dashboard_readonly_db_uri
  to   = aws_secretsmanager_secret.readonly_db_uri
}

moved {
  from = aws_secretsmanager_secret_version.dashboard_readonly_db_uri
  to   = aws_secretsmanager_secret_version.readonly_db_uri
}
