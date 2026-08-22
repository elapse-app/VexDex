# Postgres via Neon — see README.md "Database" section for why: this app
# only ever talks to it through DATABASE_URL, so any standard Postgres works,
# and Neon's free tier comfortably covers this project's scale.

resource "neon_project" "vexdex" {
  name       = "vexdex-${var.environment}"
  pg_version = 16
  region_id  = var.neon_region_id

  branch {
    name          = "production"
    database_name = "vexdex"
    role_name     = "vexdex"
  }

  default_endpoint_settings {
    # Scales to zero when idle — the pipeline only writes weekly, and the API
    # is low-traffic, so there's no reason to pay for an always-on compute.
    autoscaling_limit_min_cu = 0.25
    autoscaling_limit_max_cu = 1.0
  }
}

output "database_url" {
  description = "DATABASE_URL for this project's default branch. Note: this is the plain postgresql:// form — prefix it with postgresql+psycopg:// before using it as VexDex's DATABASE_URL (see README.md)."
  value       = neon_project.vexdex.connection_uri
  sensitive   = true
}
