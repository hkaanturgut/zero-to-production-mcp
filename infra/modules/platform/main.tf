locals {
  name = "${var.name_prefix}-${var.env}"
  # Key Vault names: 3-24 chars, globally unique.
  kv_name = substr("${var.name_prefix}${var.env}${random_string.suffix.result}", 0, 24)
  tags = merge(var.tags, {
    workload    = "dealer-mcp"
    environment = var.env
    managed_by  = "terraform"
  })
  image = "${var.acr_login_server}/dealer-mcp:${var.image_tag}"
}

data "azurerm_client_config" "current" {}

resource "random_string" "suffix" {
  length  = 4
  special = false
  upper   = false
}

# The resource group, pipeline identities and their role assignments are
# created by infra/bootstrap (the "landing zone"). This stack only fills it.
data "azurerm_resource_group" "this" {
  name = var.resource_group_name
}

# ------------------------------------------------------------------ observability

resource "azurerm_log_analytics_workspace" "this" {
  name                = "log-${local.name}"
  location            = data.azurerm_resource_group.this.location
  resource_group_name = data.azurerm_resource_group.this.name
  sku                 = "PerGB2018"
  retention_in_days   = var.env == "prod" ? 90 : 30
  tags                = local.tags
}

resource "azurerm_application_insights" "this" {
  name                = "appi-${local.name}"
  location            = data.azurerm_resource_group.this.location
  resource_group_name = data.azurerm_resource_group.this.name
  workspace_id        = azurerm_log_analytics_workspace.this.id
  application_type    = "web"
  tags                = local.tags
}

# ------------------------------------------------------------------ identity + secrets

# One user-assigned identity for both apps: pulls images and reads secrets.
# No registry passwords, no connection strings with keys.
resource "azurerm_user_assigned_identity" "apps" {
  name                = "id-${local.name}-apps"
  location            = data.azurerm_resource_group.this.location
  resource_group_name = data.azurerm_resource_group.this.name
  tags                = local.tags
}

resource "azurerm_role_assignment" "acr_pull" {
  scope                = var.acr_id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.apps.principal_id
}

resource "azurerm_key_vault" "this" {
  name                          = local.kv_name
  location                      = data.azurerm_resource_group.this.location
  resource_group_name           = data.azurerm_resource_group.this.name
  tenant_id                     = data.azurerm_client_config.current.tenant_id
  sku_name                      = "standard"
  rbac_authorization_enabled    = true
  purge_protection_enabled      = var.env == "prod"
  soft_delete_retention_days    = 7
  public_network_access_enabled = true # tighten with private endpoints in a VNet-integrated setup
  tags                          = local.tags
}

# The pipeline identity writes the secret; the apps can only read it.
resource "azurerm_role_assignment" "kv_officer_pipeline" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_role_assignment" "kv_user_apps" {
  scope                = azurerm_key_vault.this.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.apps.principal_id
}

# Service credential between the MCP server and the DMS. Generated, never typed
# by a human, never output. Rotate by tainting this resource.
resource "random_password" "dms_api_key" {
  length  = 48
  special = false
}

resource "azurerm_key_vault_secret" "dms_api_key" {
  name         = "dms-api-key"
  value        = random_password.dms_api_key.result
  key_vault_id = azurerm_key_vault.this.id
  content_type = "service-credential"
  depends_on   = [azurerm_role_assignment.kv_officer_pipeline]
}

# ------------------------------------------------------------------ container apps

resource "azurerm_container_app_environment" "this" {
  name                       = "cae-${local.name}"
  location                   = data.azurerm_resource_group.this.location
  resource_group_name        = data.azurerm_resource_group.this.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.this.id
  tags                       = local.tags
}

# The dealer system: internal ingress only. Reachable from apps in this
# environment, never from the internet.
resource "azurerm_container_app" "dms" {
  name                         = "ca-${local.name}-dms"
  container_app_environment_id = azurerm_container_app_environment.this.id
  resource_group_name          = data.azurerm_resource_group.this.name
  revision_mode                = "Single"
  tags                         = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.apps.id]
  }

  registry {
    server   = var.acr_login_server
    identity = azurerm_user_assigned_identity.apps.id
  }

  secret {
    name                = "dms-api-key"
    key_vault_secret_id = azurerm_key_vault_secret.dms_api_key.versionless_id
    identity            = azurerm_user_assigned_identity.apps.id
  }

  ingress {
    external_enabled = false
    target_port      = 8081
    transport        = "http"
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = 1
    max_replicas = 1 # in-memory demo data: exactly one replica

    container {
      name    = "dms"
      image   = local.image
      command = ["dms"]
      cpu     = 0.25
      memory  = "0.5Gi"

      env {
        name  = "PORT"
        value = "8081"
      }
      env {
        name  = "HOST"
        value = "0.0.0.0"
      }
      env {
        name        = "DMS_API_KEY"
        secret_name = "dms-api-key"
      }

      liveness_probe {
        transport = "HTTP"
        port      = 8081
        path      = "/healthz"
      }
    }
  }

  depends_on = [azurerm_role_assignment.acr_pull, azurerm_role_assignment.kv_user_apps]
}

# The MCP server: the only public entry point.
resource "azurerm_container_app" "mcp" {
  name                         = "ca-${local.name}-mcp"
  container_app_environment_id = azurerm_container_app_environment.this.id
  resource_group_name          = data.azurerm_resource_group.this.name
  # Multiple revisions: the pipeline smoke-tests a new revision before shifting traffic.
  revision_mode = "Multiple"
  tags          = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.apps.id]
  }

  registry {
    server   = var.acr_login_server
    identity = azurerm_user_assigned_identity.apps.id
  }

  secret {
    name                = "dms-api-key"
    key_vault_secret_id = azurerm_key_vault_secret.dms_api_key.versionless_id
    identity            = azurerm_user_assigned_identity.apps.id
  }

  secret {
    name  = "appinsights-connection-string"
    value = azurerm_application_insights.this.connection_string
  }

  ingress {
    external_enabled = true
    target_port      = 8080
    transport        = "http"
    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = var.min_replicas
    max_replicas = var.max_replicas

    http_scale_rule {
      name                = "http"
      concurrent_requests = "50"
    }

    container {
      name   = "mcp"
      image  = local.image
      cpu    = 0.5
      memory = "1Gi"

      env {
        name  = "AUTH_MODE"
        value = "entra"
      }
      env {
        name  = "ENTRA_TENANT_ID"
        value = data.azurerm_client_config.current.tenant_id
      }
      env {
        name  = "ENTRA_CLIENT_ID"
        value = azuread_application.mcp.client_id
      }
      env {
        name  = "DMS_BASE_URL"
        value = "http://${azurerm_container_app.dms.name}"
      }
      env {
        name        = "DMS_API_KEY"
        secret_name = "dms-api-key"
      }
      env {
        name  = "DISCOUNT_LIMIT"
        value = tostring(var.discount_limit)
      }
      env {
        name        = "APPLICATIONINSIGHTS_CONNECTION_STRING"
        secret_name = "appinsights-connection-string"
      }
      env {
        # Public URL the server advertises in its Protected Resource Metadata.
        name  = "PUBLIC_BASE_URL"
        value = "https://ca-${local.name}-mcp.${azurerm_container_app_environment.this.default_domain}"
      }

      liveness_probe {
        transport = "HTTP"
        port      = 8080
        path      = "/healthz"
      }
      readiness_probe {
        transport = "HTTP"
        port      = 8080
        path      = "/healthz"
      }
    }
  }

  depends_on = [azurerm_role_assignment.acr_pull, azurerm_role_assignment.kv_user_apps]
}
