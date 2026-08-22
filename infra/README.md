# Infrastructure

Terraform for the two pieces of infrastructure VexDex needs: a Postgres
database (Neon) and the read API's host (Azure App Service, matching what's
documented in the top-level README's "Deploy API" section today).

This exists so a future provider move is a config diff instead of redoing
manual portal work — see the main README's "Database" section. It is **not**
required to run VexDex; SETUP.md's manual steps work fine without it.

## What this does and doesn't do

- Provisions a **new** Neon project + database and a **new** Azure resource
  group / App Service. It does not touch or import any resources you already
  created manually — if you want Terraform to manage existing resources,
  `terraform import` them first.
- Wires the API's `DATABASE_URL` and `VEX_TOKENS` app settings automatically
  from the Neon output and your `vex_tokens` variable.
- Deliberately doesn't manage the GitHub Actions secrets (`update-stats.yml`,
  `deploy-api.yml`) — copy the `database_url` output into those yourself
  (see the main README's "Automated Ingestion" section).

## Usage

```bash
# 1. Credentials (as environment variables, not committed anywhere):
export NEON_API_KEY=...          # https://console.neon.tech/app/settings/api-keys
export ARM_SUBSCRIPTION_ID=...
export ARM_TENANT_ID=...
export ARM_CLIENT_ID=...
export ARM_CLIENT_SECRET=...     # or run `az login` locally instead of ARM_* vars

# 2. Fill in variables
cp terraform.tfvars.example terraform.tfvars
# edit terraform.tfvars with your real VEX_TOKENS

# 3. Standard Terraform flow
terraform init
terraform plan
terraform apply

# 4. Get the connection string and API URL
terraform output database_url   # -raw for just the value
terraform output api_url
```

## Verified

`terraform init` + `terraform validate` were run against the real
`kislerdm/neon` (v0.15.0) and `hashicorp/azurerm` (v4.81.0) provider schemas
while writing this — not just checked against documentation. `terraform
plan`/`apply` weren't run (no real credentials available in this
environment) — do that before trusting it against a real account.
