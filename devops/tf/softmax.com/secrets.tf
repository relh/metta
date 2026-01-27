resource "kubernetes_namespace" "main" {
  metadata {
    name = "softmax-com"
  }
}

resource "kubernetes_secret" "frontend" {
  metadata {
    name      = var.frontend_secret_name
    namespace = kubernetes_namespace.main.metadata[0].name
  }

  data = merge(local.common_env_vars, local.frontend_env_vars)
}
