# Created by tf/eks/argocd.tf.
data "aws_secretsmanager_secret" "argocd_webhook" {
  name = "argocd/github-webhook-secret"
}

data "aws_secretsmanager_secret_version" "argocd_webhook" {
  secret_id = data.aws_secretsmanager_secret.argocd_webhook.id
}

resource "github_repository_webhook" "argocd" {
  repository = var.github_repo

  configuration {
    url          = "https://argocd.softmax-research.net/api/webhook"
    content_type = "json"
    secret       = data.aws_secretsmanager_secret_version.argocd_webhook.secret_string
    insecure_ssl = false
  }

  active = true
  events = ["push"]
}
