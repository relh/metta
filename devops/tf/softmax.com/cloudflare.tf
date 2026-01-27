# data "cloudflare_zone" "softmax_com" {
#   filter = {
#     name = "softmax.com"
#   }
# }

# resource "cloudflare_dns_record" "softmax_com" {
#   # zone_id, not id, https://github.com/cloudflare/terraform-provider-cloudflare/issues/5174
#   zone_id = data.cloudflare_zone.softmax_com.zone_id
#   name    = "beta"
#   ttl     = 1
#   type    = "CNAME"
#   content = "softmax-com.softmax-research.net"
#   proxied = true
# }

removed {
  from = cloudflare_dns_record.softmax_com

  lifecycle {
    destroy = false
  }
}
