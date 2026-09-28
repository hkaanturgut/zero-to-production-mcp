# One-time setup, run by a platform admin with `terraform apply` (local state is
# fine here; keep it safe or migrate it into the storage account afterwards).
#
# Creates what the pipelines need before they can run:
#   * remote state storage (Entra auth only, no access keys)
#   * the shared container registry (build once, promote dev -> prod)
#   * one resource group per environment
#   * GitHub OIDC identities with least-privilege roles:
#       build  -> AcrPush on the registry (main branch only)
#       plan   -> Reader + state access (pull requests)
#       apply  -> Contributor on its env resource group (GitHub environment only)

terraform {
  required_version = ">= 1.9"
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 5.7" }
    azuread = { source = "hashicorp/azuread", version = "~> 3.10" }
    random  = { source = "hashicorp/random", version = "~> 3.7" }
  }
}

provider "azurerm" {
  features {}
  subscription_id     = var.subscription_id
  storage_use_azuread = true
}

provider "azuread" {}

variable "subscription_id" {
  type = string
}

variable "location" {
  type    = string
  default = "canadacentral"
}

variable "github_repository" {
  description = "owner/repo, e.g. hkaanturgut/mcp-dealer-assistant"
  type        = string
}

variable "environments" {
  type    = list(string)
  default = ["dev", "prod"]
}

variable "name_prefix" {
  type    = string
  default = "dealermcp"
}

locals {
  issuer   = "https://token.actions.githubusercontent.com"
  audience = ["api://AzureADTokenExchange"]
}

resource "random_string" "suffix" {
  length  = 5
  special = false
  upper   = false
}

resource "azurerm_resource_group" "shared" {
  name     = "rg-${var.name_prefix}-shared"
  location = var.location
}

# ------------------------------------------------------------------ state

resource "azurerm_storage_account" "state" {
  name                            = "st${var.name_prefix}tf${random_string.suffix.result}"
  resource_group_name             = azurerm_resource_group.shared.name
  location                        = var.location
  account_tier                    = "Standard"
  account_replication_type        = "ZRS"
  min_tls_version                 = "TLS1_2"
  shared_access_key_enabled       = false # Entra auth only
  allow_nested_items_to_be_public = false

  blob_properties {
    versioning_enabled = true # recover from a bad apply
    delete_retention_policy {
      days = 30
    }
  }
}

resource "azurerm_storage_container" "state" {
  for_each              = toset(var.environments)
  name                  = "tfstate-${each.key}"
  storage_account_id    = azurerm_storage_account.state.id
  container_access_type = "private"
}

# ------------------------------------------------------------------ registry

resource "azurerm_container_registry" "shared" {
  name                = "${var.name_prefix}acr${random_string.suffix.result}"
  resource_group_name = azurerm_resource_group.shared.name
  location            = var.location
  sku                 = "Standard"
  admin_enabled       = false # identities only
}

# ------------------------------------------------------------------ per environment

resource "azurerm_resource_group" "env" {
  for_each = toset(var.environments)
  name     = "rg-${var.name_prefix}-${each.key}"
  location = var.location
}

resource "azurerm_user_assigned_identity" "plan" {
  for_each            = toset(var.environments)
  name                = "id-gh-${var.name_prefix}-${each.key}-plan"
  resource_group_name = azurerm_resource_group.shared.name
  location            = var.location
}

resource "azurerm_user_assigned_identity" "apply" {
  for_each            = toset(var.environments)
  name                = "id-gh-${var.name_prefix}-${each.key}-apply"
  resource_group_name = azurerm_resource_group.shared.name
  location            = var.location
}

resource "azurerm_user_assigned_identity" "build" {
  name                = "id-gh-${var.name_prefix}-build"
  resource_group_name = azurerm_resource_group.shared.name
  location            = var.location
}

# Plan runs on pull requests: it can read, never change.
resource "azurerm_federated_identity_credential" "plan_pr" {
  for_each                  = toset(var.environments)
  name                      = "github-pr"
  user_assigned_identity_id = azurerm_user_assigned_identity.plan[each.key].id
  issuer                    = local.issuer
  audience                  = local.audience
  subject                   = "repo:${var.github_repository}:pull_request"
}

# Apply runs only inside the matching GitHub Environment (where approvals live).
resource "azurerm_federated_identity_credential" "apply_env" {
  for_each                  = toset(var.environments)
  name                      = "github-env-${each.key}"
  user_assigned_identity_id = azurerm_user_assigned_identity.apply[each.key].id
  issuer                    = local.issuer
  audience                  = local.audience
  subject                   = "repo:${var.github_repository}:environment:${each.key}"
}

resource "azurerm_federated_identity_credential" "build_main" {
  name                      = "github-main"
  user_assigned_identity_id = azurerm_user_assigned_identity.build.id
  issuer                    = local.issuer
  audience                  = local.audience
  subject                   = "repo:${var.github_repository}:ref:refs/heads/main"
}

resource "azurerm_role_assignment" "build_push" {
  scope                = azurerm_container_registry.shared.id
  role_definition_name = "AcrPush"
  principal_id         = azurerm_user_assigned_identity.build.principal_id
}

resource "azurerm_role_assignment" "plan_reader" {
  for_each             = toset(var.environments)
  scope                = azurerm_resource_group.env[each.key].id
  role_definition_name = "Reader"
  principal_id         = azurerm_user_assigned_identity.plan[each.key].principal_id
}

# Plan refreshes the Key Vault secret resource, so it needs to read secrets.
resource "azurerm_role_assignment" "plan_kv" {
  for_each             = toset(var.environments)
  scope                = azurerm_resource_group.env[each.key].id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.plan[each.key].principal_id
}

resource "azurerm_role_assignment" "plan_registry_reader" {
  for_each             = toset(var.environments)
  scope                = azurerm_container_registry.shared.id
  role_definition_name = "Reader"
  principal_id         = azurerm_user_assigned_identity.plan[each.key].principal_id
}

resource "azurerm_role_assignment" "apply_contributor" {
  for_each             = toset(var.environments)
  scope                = azurerm_resource_group.env[each.key].id
  role_definition_name = "Contributor"
  principal_id         = azurerm_user_assigned_identity.apply[each.key].principal_id
}

# Apply creates role assignments (AcrPull, Key Vault). Constrained with an ABAC
# condition so it can only grant these specific roles, never Owner.
resource "azurerm_role_assignment" "apply_rbac_admin" {
  for_each             = toset(var.environments)
  scope                = azurerm_resource_group.env[each.key].id
  role_definition_name = "Role Based Access Control Administrator"
  principal_id         = azurerm_user_assigned_identity.apply[each.key].principal_id
  condition_version    = "2.0"
  condition            = <<-EOT
    ((!(ActionMatches{'Microsoft.Authorization/roleAssignments/write'})) OR
     (@Request[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {4633458b-17de-408a-b874-0445c86b69e6, b86a8fe4-44ce-4948-aee5-eccb2c155cd7}))
  EOT
}

resource "azurerm_role_assignment" "apply_registry_rbac" {
  for_each             = toset(var.environments)
  scope                = azurerm_container_registry.shared.id
  role_definition_name = "Role Based Access Control Administrator"
  principal_id         = azurerm_user_assigned_identity.apply[each.key].principal_id
  condition_version    = "2.0"
  condition            = <<-EOT
    ((!(ActionMatches{'Microsoft.Authorization/roleAssignments/write'})) OR
     (@Request[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {7f951dda-4ed3-4680-a7ca-43fe172d538d}))
  EOT
}

resource "azurerm_role_assignment" "state_plan" {
  for_each             = toset(var.environments)
  scope                = azurerm_storage_container.state[each.key].id
  role_definition_name = "Storage Blob Data Contributor" # plan takes the state lock
  principal_id         = azurerm_user_assigned_identity.plan[each.key].principal_id
}

resource "azurerm_role_assignment" "state_apply" {
  for_each             = toset(var.environments)
  scope                = azurerm_storage_container.state[each.key].id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_user_assigned_identity.apply[each.key].principal_id
}

# Apply manages the server's Entra app registration. Graph app roles for a
# managed identity: create apps it owns, and assign its app roles.
data "azuread_application_published_app_ids" "well_known" {}

data "azuread_service_principal" "msgraph" {
  client_id = data.azuread_application_published_app_ids.well_known.result["MicrosoftGraph"]
}

resource "azuread_app_role_assignment" "apply_graph" {
  for_each = {
    for pair in setproduct(var.environments, ["Application.ReadWrite.OwnedBy", "AppRoleAssignment.ReadWrite.All"]) :
    "${pair[0]}-${pair[1]}" => { env = pair[0], role = pair[1] }
  }
  app_role_id         = data.azuread_service_principal.msgraph.app_role_ids[each.value.role]
  principal_object_id = azurerm_user_assigned_identity.apply[each.value.env].principal_id
  resource_object_id  = data.azuread_service_principal.msgraph.object_id
}

# Plan refreshes the app registration too, so it needs read-only Graph access.
resource "azuread_app_role_assignment" "plan_graph" {
  for_each            = toset(var.environments)
  app_role_id         = data.azuread_service_principal.msgraph.app_role_ids["Application.Read.All"]
  principal_object_id = azurerm_user_assigned_identity.plan[each.key].principal_id
  resource_object_id  = data.azuread_service_principal.msgraph.object_id
}

# ------------------------------------------------------------------ outputs -> GitHub variables

output "github_variables" {
  description = "Set these as GitHub repository / environment variables (not secrets: none are secret)."
  value = {
    AZURE_TENANT_ID       = data.azuread_client_config.current.tenant_id
    AZURE_SUBSCRIPTION_ID = var.subscription_id
    ACR_NAME              = azurerm_container_registry.shared.name
    ACR_LOGIN_SERVER      = azurerm_container_registry.shared.login_server
    ACR_ID                = azurerm_container_registry.shared.id
    TFSTATE_RG            = azurerm_resource_group.shared.name
    TFSTATE_ACCOUNT       = azurerm_storage_account.state.name
    BUILD_CLIENT_ID       = azurerm_user_assigned_identity.build.client_id
    PLAN_CLIENT_ID        = { for e in var.environments : e => azurerm_user_assigned_identity.plan[e].client_id }
    APPLY_CLIENT_ID       = { for e in var.environments : e => azurerm_user_assigned_identity.apply[e].client_id }
  }
}

data "azuread_client_config" "current" {}
