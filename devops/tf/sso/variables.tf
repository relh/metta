variable "region" {
  type    = string
  default = "us-east-1"
}

variable "sso_instance_arn" {
  type    = string
  default = "arn:aws:sso:::instance/ssoins-7223aa6587f15bea"
}

variable "identity_store_id" {
  type    = string
  default = "d-9067ceb8bd"
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
