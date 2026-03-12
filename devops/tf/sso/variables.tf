variable "region" {
  type    = string
  default = "us-east-1"
}

variable "sso_instance_arn" {
  type        = string
  description = "ARN of the IAM Identity Center instance"
}

variable "identity_store_id" {
  type        = string
  description = "Identity Store ID for IAM Identity Center"
}

variable "contractor_group_name" {
  type    = string
  default = "Contractors"
}

variable "account_ids" {
  type = map(string)
  default = {
    softmax    = "751442549699"
    tournament = "583928386201"
    sandbox    = "015142856185"
  }
}
