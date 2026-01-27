data "aws_secretsmanager_secret" "oauth_secret" {
  arn = var.oauth_secret_arn
}

data "aws_secretsmanager_secret_version" "oauth_secret" {
  secret_id = data.aws_secretsmanager_secret.oauth_secret.id
}

data "aws_secretsmanager_secret" "github_app_secret" {
  name = var.github_app_secret_name
}

data "aws_secretsmanager_secret_version" "github_app_secret" {
  secret_id = data.aws_secretsmanager_secret.github_app_secret.id
}

# copy observatory auth secret to softmax-com secrets
data "kubernetes_secret" "observatory_backend_env" {
  metadata {
    name      = "observatory-backend-env"
    namespace = "observatory"
  }
}

resource "random_password" "auth_secret" {
  length  = 32
  special = true
}

locals {
  common_env_vars = {
    DATABASE_URL = local.postgres_url
  }

  frontend_env_vars = {
    # Auth Configuration
    NEXTAUTH_SECRET      = random_password.auth_secret.result
    GOOGLE_CLIENT_ID     = jsondecode(data.aws_secretsmanager_secret_version.oauth_secret.secret_string)["client-id"]
    GOOGLE_CLIENT_SECRET = jsondecode(data.aws_secretsmanager_secret_version.oauth_secret.secret_string)["client-secret"]

    GITHUB_CLIENT_ID       = jsondecode(data.aws_secretsmanager_secret_version.github_app_secret.secret_string)["client_id"]
    GITHUB_CLIENT_SECRET   = jsondecode(data.aws_secretsmanager_secret_version.github_app_secret.secret_string)["client_secret"]
    GITHUB_INSTALLATION_ID = jsondecode(data.aws_secretsmanager_secret_version.github_app_secret.secret_string)["installation_id"]
    GITHUB_APP_PEM         = jsondecode(data.aws_secretsmanager_secret_version.github_app_secret.secret_string)["pem"]

    # Environment Configuration
    DEV_MODE              = "false"
    ALLOWED_EMAIL_DOMAINS = "stem.ai,softmax.com"

    OBSERVATORY_AUTH_SECRET = data.kubernetes_secret.observatory_backend_env.data["OBSERVATORY_AUTH_SECRET"]
  }
}
