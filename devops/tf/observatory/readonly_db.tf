resource "random_password" "readonly_db_password" {
  length  = 32
  special = true
}

resource "postgresql_role" "readonly" {
  name     = var.readonly_db_username
  login    = true
  password = random_password.readonly_db_password.result

  depends_on = [aws_db_instance.postgres]
}

resource "postgresql_grant" "readonly_database" {
  database    = aws_db_instance.postgres.db_name
  role        = postgresql_role.readonly.name
  object_type = "database"
  privileges  = ["CONNECT"]
}

resource "postgresql_grant" "readonly_schema" {
  database    = aws_db_instance.postgres.db_name
  role        = postgresql_role.readonly.name
  schema      = "public"
  object_type = "schema"
  privileges  = ["USAGE"]
}

resource "postgresql_grant" "readonly_tables" {
  database    = aws_db_instance.postgres.db_name
  role        = postgresql_role.readonly.name
  schema      = "public"
  object_type = "table"
  privileges  = ["SELECT"]
}

resource "postgresql_grant" "readonly_sequences" {
  database    = aws_db_instance.postgres.db_name
  role        = postgresql_role.readonly.name
  schema      = "public"
  object_type = "sequence"
  privileges  = ["SELECT", "USAGE"]
}

resource "postgresql_default_privileges" "readonly_tables" {
  database    = aws_db_instance.postgres.db_name
  owner       = aws_db_instance.postgres.username
  role        = postgresql_role.readonly.name
  schema      = "public"
  object_type = "table"
  privileges  = ["SELECT"]
}

resource "postgresql_default_privileges" "readonly_sequences" {
  database    = aws_db_instance.postgres.db_name
  owner       = aws_db_instance.postgres.username
  role        = postgresql_role.readonly.name
  schema      = "public"
  object_type = "sequence"
  privileges  = ["SELECT", "USAGE"]
}
