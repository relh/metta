variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "spacelift_aws_account_id" {
  type        = string
  default     = "324880187172"
  description = "Spacelift's AWS account ID (fixed, from docs: https://docs.spacelift.io/self-hosted/v0.0.7/integrations/cloud-providers/aws#configure-trust-policy)"
}

variable "spacelift_account_name" {
  type        = string
  default     = "Metta-AI"
  description = "Our Spacelift account name"
}

