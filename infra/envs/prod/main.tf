terraform {
  required_version = ">= 1.9"
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 5.7" }
    azuread = { source = "hashicorp/azuread", version = "~> 3.10" }
    random  = { source = "hashicorp/random", version = "~> 3.7" }
  }

  # Partial config: storage account, resource group and container come from
  # -backend-config in the pipeline. Entra auth via OIDC, no access keys.
  backend "azurerm" {
    key              = "platform.tfstate"
    use_azuread_auth = true
    use_oidc         = true
  }
}

provider "azurerm" {
  features {}
  storage_use_azuread = true
  use_oidc            = true
}

provider "azuread" {
  use_oidc = true
}

variable "image_tag" {
  type = string
}

variable "acr_login_server" {
  type = string
}

variable "acr_id" {
  type = string
}

variable "manager_group_object_id" {
  type    = string
  default = null
}

variable "foundry_agent_principal_ids" {
  type    = list(string)
  default = []
}

module "platform" {
  source = "../../modules/platform"

  env                         = "prod"
  resource_group_name         = "rg-dealermcp-prod"
  image_tag                   = var.image_tag
  acr_login_server            = var.acr_login_server
  acr_id                      = var.acr_id
  manager_group_object_id     = var.manager_group_object_id
  foundry_agent_principal_ids = var.foundry_agent_principal_ids
  min_replicas                = 1
  max_replicas                = 10
}

output "mcp_url" {
  value = module.platform.mcp_url
}

output "mcp_app_name" {
  value = module.platform.mcp_app_name
}

output "resource_group_name" {
  value = module.platform.resource_group_name
}

output "entra_client_id" {
  value = module.platform.entra_client_id
}

output "foundry_endpoint" {
  value = module.platform.foundry_endpoint
}

output "foundry_project_principal_id" {
  value = module.platform.foundry_project_principal_id
}
