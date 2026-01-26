variable "region" {
  type    = string
  default = "us-east-1"
}

variable "cluster_name" {
  type    = string
  default = "tournament"
}

variable "cluster_version" {
  type    = string
  default = "1.32"
}

variable "primary_account_id" {
  type        = string
  default     = "751442549699"
  description = "Primary AWS account ID (for cross-account access)"
}

variable "jobs_namespace" {
  type    = string
  default = "jobs"
}
