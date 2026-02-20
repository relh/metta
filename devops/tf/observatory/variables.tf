variable "region" {
  type    = string
  default = "us-east-1"
}

variable "eks_cluster_name" {
  type    = string
  default = "main" # name from `eks` stack
}

variable "db_instance_class" {
  type    = string
  default = "db.r6gd.2xlarge"
}

variable "db_allocated_storage" {
  type    = number
  default = 200 # GiB
}

variable "db_max_allocated_storage" {
  type    = number
  default = 1000 # GiB
}

variable "db_postgres_version" {
  type    = string
  default = "17.5"
}

variable "google_service_account_secret_arn" {
  type    = string
  default = "arn:aws:secretsmanager:us-east-1:751442549699:secret:GoogleOAuthObservatory-H7yGjS"
}

variable "dashboard_readonly_db_uri_secret_name" {
  type    = string
  default = "observatory/dashboard/readonly-db-uri"
}

variable "dashboard_readonly_db_uri" {
  description = "Readonly Postgres URI for the standalone dashboard (set via Spacelift secret env var TF_VAR_dashboard_readonly_db_uri)"
  type        = string
  default     = null
  sensitive   = true

  validation {
    condition     = var.dashboard_readonly_db_uri == null || !can(regex("://metta:", var.dashboard_readonly_db_uri))
    error_message = "dashboard_readonly_db_uri must not use the writer username 'metta'."
  }

  validation {
    condition     = var.dashboard_readonly_db_uri == null || can(regex("@${var.eks_cluster_name}-pg-ro\\.", var.dashboard_readonly_db_uri))
    error_message = "dashboard_readonly_db_uri must point to the read-replica endpoint."
  }
}
