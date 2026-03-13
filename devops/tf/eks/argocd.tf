resource "kubernetes_namespace" "argocd" {
  metadata {
    name = "argocd"
  }
}

data "aws_secretsmanager_secret" "argocd_github_oauth" {
  name = "argocd/github-oauth"
}

data "aws_secretsmanager_secret_version" "argocd_github_oauth" {
  secret_id = data.aws_secretsmanager_secret.argocd_github_oauth.id
}

data "aws_secretsmanager_secret" "metta_deploy_key" {
  name = "github/metta-deploy-key"
}

data "aws_secretsmanager_secret_version" "metta_deploy_key" {
  secret_id = data.aws_secretsmanager_secret.metta_deploy_key.id
}

resource "kubernetes_secret" "argocd_repo_metta" {
  metadata {
    name      = "repo-metta"
    namespace = kubernetes_namespace.argocd.metadata[0].name
    labels = {
      "argocd.argoproj.io/secret-type" = "repository"
    }
  }

  data = {
    type          = "git"
    url           = "git@github.com:Metta-AI/metta.git"
    sshPrivateKey = data.aws_secretsmanager_secret_version.metta_deploy_key.secret_string
  }
}

resource "random_password" "argocd_webhook_secret" {
  length  = 32
  special = false
}

resource "aws_secretsmanager_secret" "argocd_webhook" {
  name = "argocd/github-webhook-secret"
}

resource "aws_secretsmanager_secret_version" "argocd_webhook" {
  secret_id     = aws_secretsmanager_secret.argocd_webhook.id
  secret_string = random_password.argocd_webhook_secret.result
}

resource "random_password" "argocd_server_secret_key" {
  length  = 32
  special = false
}

# Terraform owns argocd-secret. The kustomize install skips creating it (via $patch: delete in
# patches/argocd-secret.yaml).
resource "kubernetes_secret" "argocd_secret" {
  metadata {
    name      = "argocd-secret"
    namespace = kubernetes_namespace.argocd.metadata[0].name
    labels = {
      "app.kubernetes.io/name"    = "argocd-secret"
      "app.kubernetes.io/part-of" = "argocd"
    }
  }

  data = {
    "server.secretkey"      = random_password.argocd_server_secret_key.result
    "webhook.github.secret" = random_password.argocd_webhook_secret.result
  }
}

resource "kubernetes_secret" "argocd_dex_github_auth" {
  metadata {
    name      = "dex-github-auth"
    namespace = kubernetes_namespace.argocd.metadata[0].name
    labels = {
      "app.kubernetes.io/part-of" = "argocd"
    }
  }

  data = {
    clientID     = jsondecode(data.aws_secretsmanager_secret_version.argocd_github_oauth.secret_string)["clientID"]
    clientSecret = jsondecode(data.aws_secretsmanager_secret_version.argocd_github_oauth.secret_string)["clientSecret"]
  }
}
