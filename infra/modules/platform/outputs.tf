output "mcp_url" {
  description = "Public MCP endpoint."
  value       = "https://${azurerm_container_app.mcp.ingress[0].fqdn}/mcp"
}

output "mcp_app_name" {
  value = azurerm_container_app.mcp.name
}

output "resource_group_name" {
  value = data.azurerm_resource_group.this.name
}

output "entra_client_id" {
  description = "Client ID of the MCP server app registration (token audience)."
  value       = azuread_application.mcp.client_id
}

output "entra_scopes" {
  value = ["api://${azuread_application.mcp.client_id}/dms.read", "api://${azuread_application.mcp.client_id}/dms.write"]
}

output "foundry_project_id" {
  value = azurerm_cognitive_account_project.sales.id
}

output "foundry_endpoint" {
  value = azurerm_cognitive_account.foundry.endpoint
}

output "foundry_project_principal_id" {
  description = "Project managed identity. Add it to foundry_agent_principal_ids to let the project's agents call the server."
  value       = azurerm_cognitive_account_project.sales.identity[0].principal_id
}
