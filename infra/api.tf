# Azure App Service for the read API — matches the manual setup documented
# in README.md "Deploy API (Azure App Service)". This captures what's
# already running there as code; nothing about the DB engine choice ties
# this to Azure specifically (see README.md "Database").

resource "azurerm_resource_group" "vexdex" {
  name     = "rg-vexdex-${var.environment}"
  location = var.azure_location
}

resource "azurerm_service_plan" "vexdex" {
  name                = "asp-vexdex-${var.environment}"
  resource_group_name = azurerm_resource_group.vexdex.name
  location            = azurerm_resource_group.vexdex.location
  os_type             = "Linux"
  sku_name            = var.azure_app_service_sku
}

resource "azurerm_linux_web_app" "vexdex" {
  name                = "vexdex-api-${var.environment}"
  resource_group_name = azurerm_resource_group.vexdex.name
  location            = azurerm_service_plan.vexdex.location
  service_plan_id     = azurerm_service_plan.vexdex.id

  site_config {
    application_stack {
      python_version = "3.12"
    }
    app_command_line = "gunicorn -k uvicorn.workers.UvicornWorker -w 2 -b 0.0.0.0:$PORT api:app"
  }

  app_settings = {
    DATABASE_URL = replace(neon_project.vexdex.connection_uri, "postgresql://", "postgresql+psycopg://")
    VEX_TOKENS   = var.vex_tokens
  }
}

output "api_url" {
  description = "The API's default hostname."
  value       = "https://${azurerm_linux_web_app.vexdex.default_hostname}"
}
