variable "region" {
  type    = string
  default = "us-east-1"
}

variable "sso_instance_arn" {
  type    = string
  default = "arn:aws:sso:::instance/ssoins-722343ea1d788ae8"
}

variable "contractor_group_id" {
  type    = string
  default = "f44884d8-70b1-70f3-392f-875e1f6d4b53"
}

variable "account_ids" {
  type = map(string)
  default = {
    softmax    = "751442549699"
    tournament = "583928386201"
    sandbox    = "015142856185"
  }
}
