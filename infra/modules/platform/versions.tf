terraform {
  required_version = ">= 1.9"
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 5.7" }
    azuread = { source = "hashicorp/azuread", version = "~> 3.10" }
    random  = { source = "hashicorp/random", version = "~> 3.7" }
  }
}
