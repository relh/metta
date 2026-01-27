variable "region" {
  type    = string
  default = "us-east-1"
}

variable "eks_cluster_name" {
  type    = string
  default = "main"
}

variable "db_postgres_version" {
  description = "The version of PostgreSQL to use"
  type        = string
  default     = "17.5"
}

variable "db_instance_class" {
  description = "The instance class for the RDS database"
  type        = string
  default     = "db.t3.micro"
}

variable "db_allocated_storage" {
  description = "The allocated storage for the RDS database (in GB)"
  type        = number
  default     = 20
}

variable "oauth_secret_arn" {
  description = "ARN of the AWS Secrets Manager secret containing OAuth credentials for Google"
  default     = "arn:aws:secretsmanager:us-east-1:751442549699:secret:softmax-infra-oauth-rLFTw6"
}

variable "github_app_secret_name" {
  description = "Name of the AWS Secrets Manager secret containing credentials for GitHub"
  default     = "github/softmax-com-app"
}


# variable "cloudflare_api_token_secret_arn" {
#   description = "Cloudflare API token"
#   default     = "arn:aws:secretsmanager:us-east-1:751442549699:secret:cloudflare/softmax-com-dns-token-ZQmiVP"
# }

variable "frontend_secret_name" {
  description = "Name of the Kubernetes secret for frontend environment variables"
  type        = string
  default     = "softmax-com-frontend-secrets"
}

variable "domain" {
  type    = string
  default = "softmax.com"
}
