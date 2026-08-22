variable "environment" {
  description = "Short environment name used in resource names (e.g. \"prod\", \"staging\")."
  type        = string
  default     = "prod"
}

variable "neon_region_id" {
  description = "Neon region — see https://neon.com/docs/introduction/regions"
  type        = string
  default     = "aws-us-east-1"
}

variable "azure_location" {
  description = "Azure region for the resource group / App Service."
  type        = string
  default     = "eastus"
}

variable "azure_app_service_sku" {
  description = "Azure App Service Plan pricing tier."
  type        = string
  default     = "B1"
}

variable "vex_tokens" {
  description = "Comma-separated VEX Events bearer tokens (VEX_TOKENS)."
  type        = string
  sensitive   = true
}
