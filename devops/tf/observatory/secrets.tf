resource "kubernetes_namespace" "observatory" {
  metadata {
    name = "observatory"
  }
}

data "aws_secretsmanager_secret" "anthropic_api_key" {
  name = "anthropic/api-key"
}

data "aws_secretsmanager_secret_version" "anthropic_api_key_version" {
  secret_id = data.aws_secretsmanager_secret.anthropic_api_key.id
}

data "aws_secretsmanager_secret" "smart_plugs_config" {
  name = "smart-plugs/founders-wing"
}

data "aws_secretsmanager_secret_version" "smart_plugs_config_version" {
  secret_id = data.aws_secretsmanager_secret.smart_plugs_config.id
}

resource "random_password" "auth_secret" {
  length  = 27
  special = false
}

locals {
  readonly_db_uri = "postgresql://${postgresql_role.readonly.name}:${urlencode(random_password.readonly_db_password.result)}@${aws_db_instance.postgres_read_replica.endpoint}/${aws_db_instance.postgres.db_name}"
}

resource "aws_secretsmanager_secret" "readonly_db_uri" {
  name = var.readonly_db_uri_secret_name
}

resource "aws_secretsmanager_secret_version" "readonly_db_uri" {
  secret_id     = aws_secretsmanager_secret.readonly_db_uri.id
  secret_string = local.readonly_db_uri

  depends_on = [
    postgresql_grant.readonly_database,
    postgresql_grant.readonly_schema,
    postgresql_grant.readonly_tables,
    postgresql_grant.readonly_sequences,
    postgresql_default_privileges.readonly_tables,
    postgresql_default_privileges.readonly_sequences,
  ]
}

resource "kubernetes_secret" "observatory_backend_env" {
  metadata {
    name      = "observatory-backend-env"
    namespace = kubernetes_namespace.observatory.metadata[0].name
  }
  data = {
    STATS_DB_URI           = "postgresql://${aws_db_instance.postgres.username}:${aws_db_instance.postgres.password}@${aws_db_instance.postgres.endpoint}/${aws_db_instance.postgres.db_name}"
    STATS_DB_READ_ONLY_URI = local.readonly_db_uri
    # used by SQL query generator
    ANTHROPIC_API_KEY = data.aws_secretsmanager_secret_version.anthropic_api_key_version.secret_string
    # bypass for token auth in app_backend, allows softmax.com -> observatory communication
    OBSERVATORY_AUTH_SECRET = random_password.auth_secret.result
    SMART_PLUGS_ENABLED     = "true"
    SMART_PLUGS_ALLOW_WRITE = "false"
    SMART_PLUGS_CONFIG_JSON = data.aws_secretsmanager_secret_version.smart_plugs_config_version.secret_string
  }
}
