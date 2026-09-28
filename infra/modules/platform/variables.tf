variable "env" {
  description = "Environment name: dev or prod."
  type        = string
  validation {
    condition     = contains(["dev", "prod"], var.env)
    error_message = "env must be dev or prod."
  }
}

variable "resource_group_name" {
  description = "Existing resource group created by infra/bootstrap."
  type        = string
}

variable "name_prefix" {
  description = "Short prefix for resource names (letters and digits only)."
  type        = string
  default     = "dealermcp"
}

variable "image_tag" {
  description = "Container image tag to deploy (git SHA). Set by the pipeline."
  type        = string
}

variable "acr_login_server" {
  description = "Shared container registry, e.g. dealermcpacr.azurecr.io. Images are built once and promoted."
  type        = string
}

variable "acr_id" {
  description = "Resource ID of the shared container registry (for the AcrPull role)."
  type        = string
}

variable "min_replicas" {
  description = "Keep at least one replica warm: interactive MCP clients should never hit a cold start."
  type        = number
  default     = 1
}

variable "max_replicas" {
  type    = number
  default = 5
}

variable "discount_limit" {
  description = "Largest discount a salesperson can apply without a manager (CAD)."
  type        = number
  default     = 500
}

variable "manager_group_object_id" {
  description = "Entra group whose members get the dms.manager app role. Null to skip."
  type        = string
  default     = null
}

variable "foundry_agent_principal_ids" {
  description = "Service principal object IDs of Foundry agent identities that may call the server (read + write roles only)."
  type        = list(string)
  default     = []
}

variable "foundry_model" {
  description = "Model deployed in the Foundry project for the demo agent."
  type = object({
    name     = string
    version  = string
    sku      = string
    capacity = number
  })
  default = {
    name     = "gpt-4.1-mini"
    version  = "2025-04-14"
    sku      = "GlobalStandard"
    capacity = 50
  }
}

variable "tags" {
  type    = map(string)
  default = {}
}
