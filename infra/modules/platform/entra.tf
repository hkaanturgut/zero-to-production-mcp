# The MCP server as an OAuth protected resource in Microsoft Entra ID.
#
#  * Delegated scopes dms.read, dms.write: what a signed-in salesperson's client asks for.
#  * App roles dms.read, dms.write (Applications): granted to Foundry agent identities.
#  * App role dms.manager (Users): granted only to the managers group. Using an app
#    role (not a scope) means no one can consent their way into manager rights.
#
# The server merges `scp` and `roles` into one permission set (src/server/auth.py).

resource "random_uuid" "ids" {
  for_each = toset(["scope_read", "scope_write", "role_read", "role_write", "role_manager"])
}

resource "azuread_application" "mcp" {
  display_name     = "Dealer Sales MCP (${var.env})"
  sign_in_audience = "AzureADMyOrg"
  owners           = [data.azurerm_client_config.current.object_id]

  api {
    # v2 tokens: aud = this app's client ID, iss = .../v2.0 (what the server validates).
    requested_access_token_version = 2

    oauth2_permission_scope {
      id                         = random_uuid.ids["scope_read"].result
      value                      = "dms.read"
      type                       = "User"
      admin_consent_display_name = "Read dealer inventory"
      admin_consent_description  = "Search cars, quote prices, estimate payments, view test-drive slots."
      user_consent_display_name  = "Read dealer inventory"
      user_consent_description   = "Let the assistant search cars and quote prices for you."
      enabled                    = true
    }

    oauth2_permission_scope {
      id                         = random_uuid.ids["scope_write"].result
      value                      = "dms.write"
      type                       = "Admin"
      admin_consent_display_name = "Manage leads and bookings"
      admin_consent_description  = "Create leads, book test drives, apply small discounts."
      enabled                    = true
    }
  }

  app_role {
    id                   = random_uuid.ids["role_read"].result
    value                = "dms.read"
    allowed_member_types = ["Application"]
    display_name         = "Agent: read inventory"
    description          = "Lets an agent identity use read tools."
    enabled              = true
  }

  app_role {
    id                   = random_uuid.ids["role_write"].result
    value                = "dms.write"
    allowed_member_types = ["Application"]
    display_name         = "Agent: leads and bookings"
    description          = "Lets an agent identity create leads and book test drives."
    enabled              = true
  }

  app_role {
    id                   = random_uuid.ids["role_manager"].result
    value                = "dms.manager"
    allowed_member_types = ["User"]
    display_name         = "Sales manager"
    description          = "Big discounts, mark sold, delete leads. Never assigned to agents."
    enabled              = true
  }
}

resource "azuread_application_identifier_uri" "mcp" {
  application_id = azuread_application.mcp.id
  identifier_uri = "api://${azuread_application.mcp.client_id}"
}

resource "azuread_service_principal" "mcp" {
  client_id                    = azuread_application.mcp.client_id
  app_role_assignment_required = false
  owners                       = [data.azurerm_client_config.current.object_id]
}

resource "azuread_app_role_assignment" "managers" {
  count               = var.manager_group_object_id == null ? 0 : 1
  app_role_id         = random_uuid.ids["role_manager"].result
  principal_object_id = var.manager_group_object_id
  resource_object_id  = azuread_service_principal.mcp.object_id
}

# Agents get read + write. There is deliberately no loop that grants dms.manager.
resource "azuread_app_role_assignment" "agent_read" {
  for_each            = toset(var.foundry_agent_principal_ids)
  app_role_id         = random_uuid.ids["role_read"].result
  principal_object_id = each.value
  resource_object_id  = azuread_service_principal.mcp.object_id
}

resource "azuread_app_role_assignment" "agent_write" {
  for_each            = toset(var.foundry_agent_principal_ids)
  app_role_id         = random_uuid.ids["role_write"].result
  principal_object_id = each.value
  resource_object_id  = azuread_service_principal.mcp.object_id
}
