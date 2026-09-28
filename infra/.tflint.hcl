# Core Terraform rules. Add the azurerm ruleset
# (github.com/terraform-linters/tflint-ruleset-azurerm) pinned to its latest
# release for Azure-specific checks such as invalid SKUs and regions.
plugin "terraform" {
  enabled = true
  preset  = "recommended"
}
