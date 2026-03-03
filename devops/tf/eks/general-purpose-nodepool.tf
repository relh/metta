# Tune the EKS Auto Mode-managed general-purpose NodePool to avoid aggressive
# underutilized evictions that churn critical observatory workloads.
resource "kubernetes_manifest" "general_purpose_nodepool_disruption" {
  manifest = {
    apiVersion = "karpenter.sh/v1"
    kind       = "NodePool"
    metadata = {
      name = "general-purpose"
    }
    spec = {
      disruption = {
        budgets = [
          {
            nodes = "10%"
          }
        ]
        consolidateAfter    = "10m"
        consolidationPolicy = "WhenEmpty"
      }
    }
  }

  field_manager {
    force_conflicts = true
    name            = "terraform"
  }

  lifecycle {
    prevent_destroy = true
  }

  depends_on = [module.eks]
}
