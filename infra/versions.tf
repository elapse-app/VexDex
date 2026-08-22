terraform {
  required_version = ">= 1.5"

  required_providers {
    neon = {
      source  = "kislerdm/neon"
      version = "~> 0.15"
    }
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

provider "neon" {
  # Reads NEON_API_KEY from the environment — generate one at
  # https://console.neon.tech/app/settings/api-keys
}

provider "azurerm" {
  features {}
  # Reads ARM_SUBSCRIPTION_ID / ARM_TENANT_ID / ARM_CLIENT_ID / ARM_CLIENT_SECRET
  # from the environment (or use `az login` for local runs).
}
