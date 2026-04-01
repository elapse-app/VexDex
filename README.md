# VexDex

VexDex pulls RobotEvents data, computes team performance metrics (OPR, DPR, CCWM, TrueSkill), and persists results to SQL.

## Features

- Async RobotEvents ingestion with retry and rate-limit handling.
- Deterministic event processing with processed-event tracking.
- SQL persistence for team metrics and event checkpoints.
- CI-ready project structure with lint and compile checks.

## Project Structure

- update_stats.py: Main pipeline entrypoint.
- api.py: FastAPI read API for teams and refresh status.
- tournament_stats.py: Match processing and rating math.
- fetch_re.py: RobotEvents API client.
- db.py: SQLAlchemy models and persistence helpers.
- config.py: Runtime config from environment variables.

## Requirements

- Python 3.12+
- Access to RobotEvents API tokens
- A configured SQL database

Install dependencies:

```bash
pip install -r requirements-dev.txt
```

## Environment Variables

Copy .env.example and fill values.

Required:

- RE_TOKENS: Comma-separated RobotEvents bearer tokens.
- Database config:
	- Preferred: DATABASE_URL
	- Fallback for SQL Server: DB_USER, DB_PASS, DB_HOST, DB_NAME

Optional:

- RE_SEASON_ID: Optional season ID override. If unset, incremental runs use the latest V5RC season from RobotEvents.
- RE_EVENT_START: ISO datetime lower bound for event fetch (default 2025-12-17T00:00:00).

## Run Pipeline

```bash
python update_stats.py
```

Manual one-time backfill for a past season:

```bash
python update_stats.py --season-backfill <season_id>
```

Behavior:

- Writes dataset refresh runs to `dataset_refresh_runs` with running/succeeded/failed status.
- Marks the dataset fresh only when a pipeline run completes successfully.
- Incremental runs target the latest V5RC season from RobotEvents unless `RE_SEASON_ID` is set.
- Uses the last processed event start as the next fetch checkpoint (falls back to RE_EVENT_START).
- Re-fetches events that were previously processed while still in progress.
- Skips events that are already processed and complete.
- `--season-backfill` fetches all events in a season (not checkpoint-limited) for manual historical population.
- Computes metrics for new events.
- Upserts team rows into team_stats.

## Run API

```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

Production server command (recommended):

```bash
gunicorn -k uvicorn.workers.UvicornWorker -w 2 -b 0.0.0.0:${PORT:-8000} api:app
```

Available endpoints:

- `GET /api/v1/health`
- `GET /api/v1/teams?limit=100&offset=0`
- `GET /api/v1/teams/{team_id}`
- `GET /api/v1/teams/by-number/{team_num}`
- `GET /api/v1/seasons`
- `GET /api/v1/seasons/{season_id}/teams?limit=100&offset=0`
- `GET /api/v1/seasons/{season_id}/teams/{team_id}`
- `GET /api/v1/seasons/{season_id}/teams/by-number/{team_num}`
- `GET /api/v1/refresh-runs/latest`
- `GET /api/v1/refresh-runs?limit=50`

## Deploy API (Azure App Service)

1. Create an Azure Web App (Linux, Python 3.12).
2. In App Service Configuration, set startup command to:

```bash
gunicorn -k uvicorn.workers.UvicornWorker -w 2 -b 0.0.0.0:$PORT api:app
```

3. Set required app settings in Azure:
	- `DATABASE_URL` (recommended) or `DB_USER` / `DB_PASS` / `DB_HOST` / `DB_NAME`
4. Add GitHub repository secrets:
	- `AZURE_WEBAPP_NAME`
	- `AZURE_WEBAPP_PUBLISH_PROFILE`
5. Push to `main`/`master` or run the `deploy-api-azure` workflow manually.

Deployment workflow:

- `.github/workflows/deploy-api.yml`

## Automated Ingestion (GitHub Actions)

Workflow:

- `.github/workflows/update-stats.yml`

Behavior:

- Runs incremental updates weekly (Monday 06:00 UTC).
- Supports manual one-time backfill through workflow dispatch input `season_backfill`.

Required repository secrets:

- `RE_TOKENS`
- `DATABASE_URL` (recommended) or `DB_USER` / `DB_PASS` / `DB_HOST` / `DB_NAME`

Optional repository secrets:

- `RE_SEASON_ID`
- `RE_EVENT_START`

## CI

GitHub Actions workflow is defined in .github/workflows/ci.yml.

Checks performed:

- Ruff linting
- Python compile check

Run checks locally:

```bash
ruff check .
python -m compileall .
```