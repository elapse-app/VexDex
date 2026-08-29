# VexDex

VexDex pulls VEX Events data (matches, rankings, skills, awards, team profiles), computes advanced team performance metrics (OPR, DPR, CCWM, TrueSkill, win/loss records, ranking-tiebreaker averages, skills rankings, qualification tracking), and persists results to Postgres.

## Features

- Async VEX Events ingestion with retry and rate-limit handling.
- Deterministic event processing with processed-event tracking.
- Win/loss record (overall, qualification-only, elimination-only), with qualification results trusted from VEX's authoritative rankings data rather than inferred from raw scores (a disqualification or other ruling can flip a match's official result without changing its score).
- Ranking-tiebreaker averages: autonomous points (AP), win points (WP), and an estimated autonomous win point (AWP) rate, derived from the official VRC/V5RC point formula (2 WP/win, 1 WP/tie, +1 WP per AWP).
- Skills scores (driver + programming) and season-wide skills rankings — globally, by region, and again excluding teams that already hold a qualifying award ("unqualed" rank).
- World/regional qualification tracking from event awards data.
- Event-by-event rating trend per team (the thing a mutable running average could never answer: is this team improving?).
- Strength of schedule (average opponent OPR faced) and a field-strength z-score, so a small local event and a Worlds-caliber field are comparable.
- Season percentile ranks (CCWM, TrueSkill) and a v1 alliance pick-list composite score.
- Postgres persistence for team metrics and event checkpoints.
- CI-ready project structure with lint and compile checks.

## Project Structure

- update_stats.py: Main pipeline entrypoint.
- api.py: FastAPI read API for teams and refresh status.
- tournament_stats.py: Match/rankings/skills/awards processing and rating math.
- fetch_vex.py: VEX Events API client.
- db.py: SQLAlchemy models and persistence helpers.
- config.py: Runtime config from environment variables.
- event.py / match.py / skill.py / award.py / team_profile.py: raw API payload parsing.

## Data Model

- `teams` / `events`: identity tables. `teams.team_name`/`grade`/`region` come from a one-time `/teams/{id}` profile fetch per team, not refetched once known.
- `team_event_results`: one immutable row per team per event — win/loss record (total/qual/elim), AP/WP/AWP, OPR/DPR/CCWM, strength of schedule, a field-strength z-score, a TrueSkill snapshot, skills scores, and that event's qualification flags. Never updated after insert — this is the source of truth.
- `team_season_summary`: derived from `team_event_results` (+ `teams` for region). Season win/loss totals, averaged/weighted AP/WP/AWP, OPR/DPR/CCWM/SOS averages and bests, the team's latest TrueSkill state, season-best skills score with global/region/unqualed ranks, season qualification flags, season percentile ranks (CCWM, TrueSkill), and a pick-list composite score. Safe to drop and rebuild from the fact table at any time.
- `team_awards`: one row per award a team won at an event (title + qualifications) — the actual history behind the qualed_worlds/qualed_regionals flags.
- `dataset_refresh_runs`: audit log of pipeline runs.

## Requirements

- Python 3.12+
- Access to VEX Events API tokens
- A Postgres database

Install dependencies:

```bash
pip install -r requirements-dev.txt
```

## Environment Variables

Copy .env.example and fill values.

Required:

- VEX_TOKENS: Comma-separated VEX Events bearer tokens.
- DATABASE_URL: Postgres connection string, e.g. `postgresql+psycopg://user:pass@host/dbname`.

Optional:

- VEX_SEASON_ID: Optional season ID override. If unset, incremental runs use the latest V5RC season from VEX Events.
- VEX_EVENT_START: ISO datetime lower bound for event fetch (default 2025-12-17T00:00:00).

API host only:

- RUN_DB_MIGRATE: if set, `api.py` runs `ensure_schema` at startup. Leave unset in
  production — schema changes are applied once per release (Fly `release_command`
  in `fly.toml`). Handy for local dev / one-off boxes.
- RESPONSE_CACHE_TTL_SECONDS: in-process GET response cache TTL (default 120; set
  `0` to disable and emit `Cache-Control: no-store`).
- RESPONSE_CACHE_MAX_ENTRIES: cap on cached responses per worker (default 512).
- For the API, point DATABASE_URL at Neon's **pooled** (`-pooler`) endpoint; keep
  the direct URL for the pipeline and migrations.

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
- Incremental runs target the latest V5RC season from VEX Events unless `VEX_SEASON_ID` is set.
- Uses the last processed event start as the next fetch checkpoint (falls back to VEX_EVENT_START).
- Re-fetches events that were previously processed while still in progress.
- Skips events that are already processed and complete.
- `--season-backfill` fetches all events in a season (not checkpoint-limited) for manual historical population.
- Events are always scored in chronological order (by event start), regardless of the order the API returns them — TrueSkill is a running belief that only makes sense processed in real match order.
- Ignores scheduled-but-not-yet-played matches (`started` is null) — they show up in the API with a placeholder 0-0 score and must not feed OPR/DPR/TrueSkill/win-loss.
- Fetches a `/teams/{id}` profile once per team the first time it's seen (name/grade/region), not on every run.
- Writes one immutable row per team per event into `team_event_results`, then rebuilds `team_season_summary` (win/loss totals, AP/WP/AWP, OPR/DPR/CCWM averages and bests, the team's most recent TrueSkill snapshot, season-best skills score with global/region/unqualed ranks, and qualification flags) from those rows.

## Run API

```bash
uvicorn api:app --host 0.0.0.0 --port 8000
```

Production server command (recommended):

```bash
gunicorn -k uvicorn.workers.UvicornWorker -w 2 -b 0.0.0.0:${PORT:-8000} api:app
```

Available endpoints (all except `/health` require a bearer token — see
[API Authentication](#api-authentication)):

- `GET /api/v1/health`
- `GET /api/v1/teams?limit=100&offset=0` — current (latest) season leaderboard
- `GET /api/v1/teams/{team_id}`
- `GET /api/v1/teams/by-number/{team_num}`
- `GET /api/v1/seasons`
- `GET /api/v1/seasons/{season_id}/teams?limit=100&offset=0&sort=ts` — `sort` is one of `ts` (default), `pick_list`, `ccwm`, `opr`
- `GET /api/v1/seasons/{season_id}/teams/{team_id}`
- `GET /api/v1/seasons/{season_id}/teams/by-number/{team_num}`
- `GET /api/v1/seasons/{season_id}/teams/{team_id}/trend` — every event this team competed in this season, chronologically, with OPR/DPR/CCWM/SOS/TrueSkill at each point
- `GET /api/v1/seasons/{season_id}/teams/{team_id}/awards` — every award this team has won this season, chronologically
- `GET /api/v1/events/{event_id}/pick-list?exclude=<team_id>&limit=20` — alliance pick-list for the teams actually registered at this event, ranked by pick_list_score; `exclude` is repeatable (your own team, anyone already picked)
- `GET /api/v1/refresh-runs/latest`
- `GET /api/v1/refresh-runs?limit=50`

## API Authentication

Every endpoint except `GET /api/v1/health` requires an API token, passed as a
bearer header:

```
Authorization: Bearer <token>
```

Requests without a valid, non-revoked token get `401`. Tokens are stored in the
`api_tokens` table (only a SHA-256 hash is kept) and managed with the
`manage_tokens.py` CLI, which talks to whatever database `DATABASE_URL` points
at:

```bash
python manage_tokens.py create --label frontend   # prints the raw token once
python manage_tokens.py list
python manage_tokens.py revoke --label frontend    # or: --id 3
```

To issue the first production token, run the CLI against the production database
(e.g. `fly ssh console -C "python manage_tokens.py create --label frontend"`, or
export the production `DATABASE_URL` locally). Until at least one token exists,
every data endpoint returns `401`.

## Database

Any Postgres instance works — the app only ever talks to it through a single
`DATABASE_URL`, so a hobby-tier managed Postgres (Neon, Supabase, RDS, ...) is a
config change, not a code change. Avoid provider-specific extensions (e.g.
Supabase auth/storage) so the database itself stays a portable, standard Postgres
instance. VexDex runs on Neon.

## Deploy API (Fly.io)

Config lives in `fly.toml` (app `vexdex`, region `iad`) and `Dockerfile`.

1. One-time: `fly launch` / `fly apps create vexdex`, then set secrets:
   ```bash
   fly secrets set DATABASE_URL='postgresql+psycopg://…-pooler.…/db' VEX_TOKENS='…'
   ```
   Use Neon's **pooled** (`-pooler`) host here; keep the direct URL for the
   ingestion workflow's `DATABASE_URL` secret.
2. `fly scale count 2` — two machines for rolling deploys and redundancy.
3. Push to `main` touching `api.py` / `db.py` / `fly.toml` / `Dockerfile` /
   `requirements.txt` → `.github/workflows/deploy-api.yml` runs
   `flyctl deploy --remote-only` (needs the `FLY_API_TOKEN` secret).
4. Each deploy runs `[deploy] release_command` in `fly.toml` to apply the schema
   (`db.ensure_schema`). Then mint the first API token (see **API Authentication**).

### Hosting & scaling notes

- **No scale-to-zero:** `min_machines_running = 1` keeps a machine warm so
  clients (e.g. the Elapse app) never hit a cold start.
- **Caching does the heavy lifting.** The dataset only changes when the weekly
  pipeline runs, so every GET carries
  `Cache-Control: public, max-age=120, s-maxage=600, stale-while-revalidate=86400`
  and the app keeps a short in-process response cache (see the env vars above).
  A burst of identical requests collapses to ~one DB query per endpoint per
  worker per TTL window. Auth is still enforced on cache hits.
- **DB connections:** `get_engine()` uses `pool_size=5, max_overflow=5,
  pool_recycle=300`; the pooled Neon endpoint absorbs bursts across workers.

Deployment workflow: `.github/workflows/deploy-api.yml`

## Automated Ingestion (GitHub Actions)

Workflow:

- `.github/workflows/update-stats.yml`

Behavior:

- Runs incremental updates weekly (Monday 06:00 UTC).
- Supports manual one-time backfill through workflow dispatch input `season_backfill`.

Required repository secrets:

- `VEX_TOKENS`
- `DATABASE_URL`

Optional repository secrets:

- `VEX_SEASON_ID`
- `VEX_EVENT_START`

## CI

GitHub Actions workflow is defined in .github/workflows/ci.yml.

Checks performed:

- Ruff linting
- Python compile check
- Unit tests against sqlite (fast, isolated per test)
- `tests/test_db_pipeline.py` re-run against a real Postgres service container — sqlite silently diverges from Postgres on some things (e.g. it drops tzinfo on `DateTime(timezone=True)` columns on read-back), so the schema/persistence layer is verified against the actual production engine on every push.

Run checks locally:

```bash
ruff check .
python -m compileall .
pytest -q
pytest --cov=. --cov-report=term-missing
RUN_INTEGRATION_TESTS=1 VEX_TOKENS=your_token pytest -q -m integration

# optional: also verify against real Postgres instead of sqlite
TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost/vexdex_test pytest -q tests/test_db_pipeline.py
```

Notes:

- Integration tests make real HTTP calls to VEX Events and are skipped unless `RUN_INTEGRATION_TESTS=1` is set.
- Keep default CI on unit tests (`pytest -q`) for reliability; run integration tests separately when needed.