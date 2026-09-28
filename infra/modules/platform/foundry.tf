# Microsoft Foundry: the enterprise client that calls our MCP server.
# The agent itself (instructions + MCP tool connection) is data-plane config,
# created by scripts/foundry_agent.py in the pipeline, not by Terraform.

resource "azurerm_cognitive_account" "foundry" {
  name                       = "aif-${local.name}-${random_string.suffix.result}"
  location                   = data.azurerm_resource_group.this.location
  resource_group_name        = data.azurerm_resource_group.this.name
  kind                       = "AIServices"
  sku_name                   = "S0"
  custom_subdomain_name      = "aif-${local.name}-${random_string.suffix.result}"
  project_management_enabled = true
  local_auth_enabled         = false # Entra ID only, no API keys
  tags                       = local.tags

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_cognitive_account_project" "sales" {
  name                 = "sales-assistant"
  cognitive_account_id = azurerm_cognitive_account.foundry.id
  location             = data.azurerm_resource_group.this.location
  description          = "Sales assistant agent that calls the dealer MCP server"
  display_name         = "Sales assistant (${var.env})"

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_cognitive_deployment" "model" {
  name                 = var.foundry_model.name
  cognitive_account_id = azurerm_cognitive_account.foundry.id

  model {
    format  = "OpenAI"
    name    = var.foundry_model.name
    version = var.foundry_model.version
  }

  sku {
    name     = var.foundry_model.sku
    capacity = var.foundry_model.capacity
  }
}
