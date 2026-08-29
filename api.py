from __future__ import annotations

import os
import time
from collections import OrderedDict
from collections.abc import Iterator
from datetime import datetime
from threading import Lock
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from db import (
    DatasetRefreshRunRecord,
    EventRecord,
    TeamAwardRecord,
    TeamEventResultRecord,
    TeamRecord,
    TeamSeasonSummaryRecord,
    ensure_schema,
    get_engine,
    get_latest_season_id,
    verify_api_token,
)

engine = get_engine()
# Schema creation is a deploy-time step (Fly `release_command`), not something
# every machine boot / gunicorn worker fork should re-run against Postgres.
# Set RUN_DB_MIGRATE=1 to opt in (local dev, one-off boxes).
if os.getenv("RUN_DB_MIGRATE"):
    ensure_schema(engine)

app = FastAPI(
    title="VexDex API",
    version="0.1.0",
    description="Read API for VEX team analytics and refresh status.",
)

# --- Response caching -------------------------------------------------------
#
# The dataset only changes when the weekly ingestion pipeline runs, so GET
# responses are safe to cache for a couple of minutes. A short in-process TTL
# cache collapses a burst of identical requests (competition-morning traffic
# from the Elapse app) into one DB query per endpoint per worker per window;
# the Cache-Control header lets clients and any CDN in front do the same.

_CACHE_TTL_SECONDS = float(os.getenv("RESPONSE_CACHE_TTL_SECONDS", "120"))
_CACHE_MAX_ENTRIES = int(os.getenv("RESPONSE_CACHE_MAX_ENTRIES", "512"))
_NO_CACHE_PATHS = {"/api/v1/health", "/docs", "/redoc", "/openapi.json"}

_cache_lock = Lock()
# key -> (expires_at_monotonic, body_bytes, media_type)
_response_cache: OrderedDict[str, tuple[float, bytes, str]] = OrderedDict()

if _CACHE_TTL_SECONDS > 0:
    _CACHE_CONTROL = (
        f"public, max-age={int(_CACHE_TTL_SECONDS)}, "
        "s-maxage=600, stale-while-revalidate=86400"
    )
else:
    _CACHE_CONTROL = "no-store"


def _cache_get(key: str) -> tuple[bytes, str] | None:
    now = time.monotonic()
    with _cache_lock:
        entry = _response_cache.get(key)
        if entry is None:
            return None
        expires_at, body, media = entry
        if expires_at <= now:
            _response_cache.pop(key, None)
            return None
        _response_cache.move_to_end(key)
        return body, media


def _cache_put(key: str, body: bytes, media: str) -> None:
    with _cache_lock:
        _response_cache[key] = (time.monotonic() + _CACHE_TTL_SECONDS, body, media)
        _response_cache.move_to_end(key)
        while len(_response_cache) > _CACHE_MAX_ENTRIES:
            _response_cache.popitem(last=False)


def _token_from(request: Request) -> str | None:
    scheme, _, param = request.headers.get("Authorization", "").partition(" ")
    return param.strip() if scheme.lower() == "bearer" and param.strip() else None


@app.middleware("http")
async def cache_and_cache_headers(request: Request, call_next):
    if request.method != "GET" or request.url.path in _NO_CACHE_PATHS:
        return await call_next(request)

    key = f"{request.url.path}?{request.url.query}"

    # Only serve a cached body to a caller that still presents a valid token —
    # the auth dependency does not run on this fast path. verify_api_token hits
    # the DB, so keep it off the event loop.
    if _CACHE_TTL_SECONDS > 0:
        hit = _cache_get(key)
        if hit is not None:
            token = _token_from(request)
            if token and await run_in_threadpool(verify_api_token, engine, token) is not None:
                body, media = hit
                cached = Response(content=body, media_type=media)
                cached.headers["Cache-Control"] = _CACHE_CONTROL
                cached.headers["X-Cache"] = "HIT"
                return cached

    response = await call_next(request)

    if response.status_code != 200:
        # Never let an auth failure or 404 be cached by a client or CDN.
        response.headers["Cache-Control"] = "no-store"
        return response

    body = b"".join([chunk async for chunk in response.body_iterator])
    media = response.media_type or "application/json"
    if _CACHE_TTL_SECONDS > 0:
        _cache_put(key, body, media)
    stored = Response(content=body, status_code=200, media_type=media)
    stored.headers.update(response.headers)
    stored.headers["Cache-Control"] = _CACHE_CONTROL
    stored.headers["X-Cache"] = "MISS" if _CACHE_TTL_SECONDS > 0 else "DISABLED"
    return stored


class TeamSeasonResponse(BaseModel):
    season_id: int
    team_id: int
    team_num: str
    team_name: str | None = None
    grade: str | None = None
    region: str | None = None

    events_count: int
    matches_played: int

    total_wins: int
    total_losses: int
    total_draws: int
    total_winrate: float
    qual_wins: int
    qual_losses: int
    qual_draws: int
    qual_winrate: float
    elim_wins: int
    elim_losses: int
    elim_draws: int
    elim_winrate: float

    avg_ap: float
    avg_wp: float
    avg_awp: float

    opr_avg: float
    opr_best: float
    dpr_avg: float
    dpr_best: float
    ccwm_avg: float
    ccwm_best: float
    sos_avg: float
    field_strength_z_avg: float

    percentile_ccwm: float | None
    percentile_ts: float | None
    pick_list_score: float | None

    ts_mu: float
    ts_sigma: float
    ts_exposed: float
    ts_rank: int

    skills_driver: int | None
    skills_prog: int | None
    skills_total: int | None
    skills_global_rank: int | None
    skills_region_rank: int | None
    unqualed_worlds_skills_global_rank: int | None
    unqualed_regionals_skills_region_rank: int | None

    qualed_worlds: bool
    qualed_regionals: bool

    updated_at: datetime


class TeamLeaderboardResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[TeamSeasonResponse]


class RefreshRunResponse(BaseModel):
    run_id: int
    season_id: int
    status: str
    events_processed: int
    teams_upserted: int
    error_message: str | None
    started_at: datetime
    completed_at: datetime | None
    dataset_fresh: bool


class RefreshRunsResponse(BaseModel):
    total: int
    limit: int
    items: list[RefreshRunResponse]


class SeasonSummaryResponse(BaseModel):
    season_id: int
    teams: int
    last_updated: datetime


class TeamEventTrendPoint(BaseModel):
    event_id: int
    event_sku: str
    event_name: str
    event_start: datetime
    matches_played: int
    opr: float
    dpr: float
    ccwm: float
    sos: float
    field_strength_z: float
    ts_mu: float
    ts_sigma: float
    ts_exposed: float
    ts_rank: int
    skills_total: int | None


class TeamEventTrendResponse(BaseModel):
    season_id: int
    team_id: int
    team_num: str
    points: list[TeamEventTrendPoint]


class TeamAwardEntry(BaseModel):
    event_id: int
    event_sku: str
    event_name: str
    event_start: datetime
    title: str
    qualifications: list[str]


class TeamAwardHistoryResponse(BaseModel):
    season_id: int
    team_id: int
    team_num: str
    awards: list[TeamAwardEntry]


class PickListEntry(BaseModel):
    team_id: int
    team_num: str
    team_name: str | None
    pick_list_score: float | None
    percentile_ccwm: float | None
    ccwm_avg: float
    skills_total: int | None
    avg_awp: float


class PickListResponse(BaseModel):
    event_id: int
    season_id: int
    items: list[PickListEntry]


def get_db() -> Iterator[Session]:
    with Session(engine) as session:
        yield session


DbSession = Annotated[Session, Depends(get_db)]

_bearer = HTTPBearer(auto_error=False, description="VexDex API token")


def require_api_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> None:
    token = credentials.credentials if credentials else None
    if not token or verify_api_token(engine, token) is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API token",
            headers={"WWW-Authenticate": "Bearer"},
        )


# Every data route hangs off this router, so authentication is the default —
# a new endpoint added here is protected without any extra wiring. Only
# deliberately-public routes (health) stay on `app` directly.
router = APIRouter(dependencies=[Depends(require_api_token)])


def _to_team_response(row: TeamSeasonSummaryRecord, team: TeamRecord | None) -> TeamSeasonResponse:
    return TeamSeasonResponse(
        season_id=row.season_id,
        team_id=row.team_id,
        team_num=row.team_num,
        team_name=team.team_name if team else None,
        grade=team.grade if team else None,
        region=team.region if team else None,
        events_count=row.events_count,
        matches_played=row.matches_played,
        total_wins=row.total_wins,
        total_losses=row.total_losses,
        total_draws=row.total_draws,
        total_winrate=row.total_winrate,
        qual_wins=row.qual_wins,
        qual_losses=row.qual_losses,
        qual_draws=row.qual_draws,
        qual_winrate=row.qual_winrate,
        elim_wins=row.elim_wins,
        elim_losses=row.elim_losses,
        elim_draws=row.elim_draws,
        elim_winrate=row.elim_winrate,
        avg_ap=row.avg_ap,
        avg_wp=row.avg_wp,
        avg_awp=row.avg_awp,
        opr_avg=row.opr_avg,
        opr_best=row.opr_best,
        dpr_avg=row.dpr_avg,
        dpr_best=row.dpr_best,
        ccwm_avg=row.ccwm_avg,
        ccwm_best=row.ccwm_best,
        sos_avg=row.sos_avg,
        field_strength_z_avg=row.field_strength_z_avg,
        percentile_ccwm=row.percentile_ccwm,
        percentile_ts=row.percentile_ts,
        pick_list_score=row.pick_list_score,
        ts_mu=row.ts_mu,
        ts_sigma=row.ts_sigma,
        ts_exposed=row.ts_exposed,
        ts_rank=row.ts_rank,
        skills_driver=row.skills_driver,
        skills_prog=row.skills_prog,
        skills_total=row.skills_total,
        skills_global_rank=row.skills_global_rank,
        skills_region_rank=row.skills_region_rank,
        unqualed_worlds_skills_global_rank=row.unqualed_worlds_skills_global_rank,
        unqualed_regionals_skills_region_rank=row.unqualed_regionals_skills_region_rank,
        qualed_worlds=row.qualed_worlds,
        qualed_regionals=row.qualed_regionals,
        updated_at=row.updated_at,
    )


def _to_refresh_run_response(row: DatasetRefreshRunRecord) -> RefreshRunResponse:
    return RefreshRunResponse(
        run_id=row.run_id,
        season_id=row.season_id,
        status=row.status,
        events_processed=row.events_processed,
        teams_upserted=row.teams_upserted,
        error_message=row.error_message,
        started_at=row.started_at,
        completed_at=row.completed_at,
        dataset_fresh=row.dataset_fresh,
    )


def _require_latest_season_id(db: DbSession) -> int:
    season_id = get_latest_season_id(db.get_bind())
    if season_id is None:
        raise HTTPException(status_code=404, detail="No season data available yet")
    return season_id


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/v1/teams", response_model=TeamLeaderboardResponse)
def list_current_teams(
    db: DbSession,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="ts", pattern="^(ts|pick_list|ccwm|opr)$"),
) -> TeamLeaderboardResponse:
    return list_teams_for_season(
        _require_latest_season_id(db), db, limit=limit, offset=offset, sort=sort
    )


@router.get("/api/v1/teams/{team_id}", response_model=TeamSeasonResponse)
def get_current_team_by_id(team_id: int, db: DbSession) -> TeamSeasonResponse:
    return get_team_for_season_by_id(_require_latest_season_id(db), team_id, db)


@router.get("/api/v1/teams/by-number/{team_num}", response_model=TeamSeasonResponse)
def get_current_team_by_number(team_num: str, db: DbSession) -> TeamSeasonResponse:
    return get_team_for_season_by_number(_require_latest_season_id(db), team_num, db)


@router.get("/api/v1/seasons", response_model=list[SeasonSummaryResponse])
def list_historical_seasons(db: DbSession) -> list[SeasonSummaryResponse]:
    rows = db.execute(
        select(
            TeamSeasonSummaryRecord.season_id,
            func.count().label("teams"),
            func.max(TeamSeasonSummaryRecord.updated_at).label("last_updated"),
        )
        .group_by(TeamSeasonSummaryRecord.season_id)
        .order_by(TeamSeasonSummaryRecord.season_id.desc())
    ).all()

    return [
        SeasonSummaryResponse(
            season_id=int(row[0]),
            teams=int(row[1]),
            last_updated=row[2],
        )
        for row in rows
    ]


_LEADERBOARD_SORTS = {
    # default: TrueSkill rank, best first
    "ts": (TeamSeasonSummaryRecord.ts_rank.asc(), desc(TeamSeasonSummaryRecord.ts_exposed)),
    # alliance pick-list order — nulls (no data yet) sort last
    "pick_list": (desc(TeamSeasonSummaryRecord.pick_list_score),),
    "ccwm": (desc(TeamSeasonSummaryRecord.ccwm_avg),),
    "opr": (desc(TeamSeasonSummaryRecord.opr_avg),),
}


@router.get("/api/v1/seasons/{season_id}/teams", response_model=TeamLeaderboardResponse)
def list_teams_for_season(
    season_id: int,
    db: DbSession,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="ts", pattern="^(ts|pick_list|ccwm|opr)$"),
) -> TeamLeaderboardResponse:
    total = db.execute(
        select(func.count())
        .select_from(TeamSeasonSummaryRecord)
        .where(TeamSeasonSummaryRecord.season_id == season_id)
    ).scalar_one()

    rows = db.execute(
        select(TeamSeasonSummaryRecord, TeamRecord)
        .join(TeamRecord, TeamRecord.team_id == TeamSeasonSummaryRecord.team_id)
        .where(TeamSeasonSummaryRecord.season_id == season_id)
        .order_by(*_LEADERBOARD_SORTS[sort], TeamSeasonSummaryRecord.team_num.asc())
        .offset(offset)
        .limit(limit)
    ).all()

    items = [_to_team_response(row, team) for row, team in rows]
    return TeamLeaderboardResponse(total=total, limit=limit, offset=offset, items=items)


@router.get("/api/v1/seasons/{season_id}/teams/{team_id}", response_model=TeamSeasonResponse)
def get_team_for_season_by_id(season_id: int, team_id: int, db: DbSession) -> TeamSeasonResponse:
    row = db.execute(
        select(TeamSeasonSummaryRecord, TeamRecord)
        .join(TeamRecord, TeamRecord.team_id == TeamSeasonSummaryRecord.team_id)
        .where(TeamSeasonSummaryRecord.season_id == season_id)
        .where(TeamSeasonSummaryRecord.team_id == team_id)
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Team not found for this season")
    summary, team = row
    return _to_team_response(summary, team)


@router.get(
    "/api/v1/seasons/{season_id}/teams/by-number/{team_num}",
    response_model=TeamSeasonResponse,
)
def get_team_for_season_by_number(
    season_id: int,
    team_num: str,
    db: DbSession,
) -> TeamSeasonResponse:
    row = db.execute(
        select(TeamSeasonSummaryRecord, TeamRecord)
        .join(TeamRecord, TeamRecord.team_id == TeamSeasonSummaryRecord.team_id)
        .where(TeamSeasonSummaryRecord.season_id == season_id)
        .where(TeamSeasonSummaryRecord.team_num == team_num)
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Team not found for this season")
    summary, team = row
    return _to_team_response(summary, team)


@router.get(
    "/api/v1/seasons/{season_id}/teams/{team_id}/trend",
    response_model=TeamEventTrendResponse,
)
def get_team_trend(season_id: int, team_id: int, db: DbSession) -> TeamEventTrendResponse:
    """Every event this team competed in this season, in chronological order
    — OPR/DPR/CCWM/TrueSkill/SOS at each point in time, not just the season
    average. This is the one thing the mutable running-average model this
    schema replaced could never answer: is this team improving?"""
    rows = db.execute(
        select(TeamEventResultRecord, EventRecord)
        .join(EventRecord, EventRecord.event_id == TeamEventResultRecord.event_id)
        .where(TeamEventResultRecord.season_id == season_id)
        .where(TeamEventResultRecord.team_id == team_id)
        .order_by(EventRecord.event_start.asc())
    ).all()
    if not rows:
        raise HTTPException(status_code=404, detail="No event results for this team in this season")

    team = db.get(TeamRecord, team_id)
    team_num = team.team_num if team else str(team_id)

    points = [
        TeamEventTrendPoint(
            event_id=event.event_id,
            event_sku=event.sku,
            event_name=event.name,
            event_start=event.event_start,
            matches_played=result.total_matches,
            opr=result.opr,
            dpr=result.dpr,
            ccwm=result.ccwm,
            sos=result.sos,
            field_strength_z=result.field_strength_z,
            ts_mu=result.ts_mu,
            ts_sigma=result.ts_sigma,
            ts_exposed=result.ts_exposed,
            ts_rank=result.ts_rank,
            skills_total=result.skills_total,
        )
        for result, event in rows
    ]
    return TeamEventTrendResponse(season_id=season_id, team_id=team_id, team_num=team_num, points=points)


@router.get(
    "/api/v1/seasons/{season_id}/teams/{team_id}/awards",
    response_model=TeamAwardHistoryResponse,
)
def get_team_award_history(season_id: int, team_id: int, db: DbSession) -> TeamAwardHistoryResponse:
    """Every award this team has won this season, chronologically — the raw
    history behind the qualed_worlds/qualed_regionals flags on the summary."""
    rows = db.execute(
        select(TeamAwardRecord, EventRecord)
        .join(EventRecord, EventRecord.event_id == TeamAwardRecord.event_id)
        .where(TeamAwardRecord.season_id == season_id)
        .where(TeamAwardRecord.team_id == team_id)
        .order_by(EventRecord.event_start.asc())
    ).all()

    team = db.get(TeamRecord, team_id)
    team_num = team.team_num if team else str(team_id)

    awards = [
        TeamAwardEntry(
            event_id=event.event_id,
            event_sku=event.sku,
            event_name=event.name,
            event_start=event.event_start,
            title=award.title,
            qualifications=award.qualifications,
        )
        for award, event in rows
    ]
    return TeamAwardHistoryResponse(season_id=season_id, team_id=team_id, team_num=team_num, awards=awards)


@router.get("/api/v1/events/{event_id}/pick-list", response_model=PickListResponse)
def get_event_pick_list(
    event_id: int,
    db: DbSession,
    exclude: list[int] = Query(default_factory=list),  # noqa: B008 — default_factory avoids the mutable-default issue this rule checks for
    limit: int = Query(default=20, ge=1, le=100),
) -> PickListResponse:
    """Alliance pick-list for the teams actually registered at this event,
    ranked by season pick_list_score. Pass `exclude` (repeatable) for your own
    team and anyone already picked — you can't pick a team twice."""
    event = db.get(EventRecord, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    rows = db.execute(
        select(TeamSeasonSummaryRecord, TeamRecord)
        .join(TeamRecord, TeamRecord.team_id == TeamSeasonSummaryRecord.team_id)
        .where(TeamSeasonSummaryRecord.season_id == event.season_id)
        .where(
            TeamSeasonSummaryRecord.team_id.in_(
                select(TeamEventResultRecord.team_id).where(
                    TeamEventResultRecord.event_id == event_id
                )
            )
        )
        .where(TeamSeasonSummaryRecord.team_id.notin_(exclude))
        .order_by(desc(TeamSeasonSummaryRecord.pick_list_score).nulls_last())
        .limit(limit)
    ).all()

    items = [
        PickListEntry(
            team_id=summary.team_id,
            team_num=summary.team_num,
            team_name=team.team_name if team else None,
            pick_list_score=summary.pick_list_score,
            percentile_ccwm=summary.percentile_ccwm,
            ccwm_avg=summary.ccwm_avg,
            skills_total=summary.skills_total,
            avg_awp=summary.avg_awp,
        )
        for summary, team in rows
    ]
    return PickListResponse(event_id=event_id, season_id=event.season_id, items=items)


@router.get("/api/v1/refresh-runs/latest", response_model=RefreshRunResponse)
def get_latest_refresh_run(db: DbSession) -> RefreshRunResponse:
    row = db.execute(
        select(DatasetRefreshRunRecord)
        .order_by(DatasetRefreshRunRecord.started_at.desc(), DatasetRefreshRunRecord.run_id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="No refresh runs found")
    return _to_refresh_run_response(row)


@router.get("/api/v1/refresh-runs", response_model=RefreshRunsResponse)
def get_refresh_runs(
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
) -> RefreshRunsResponse:
    total = db.execute(select(func.count()).select_from(DatasetRefreshRunRecord)).scalar_one()

    rows = db.execute(
        select(DatasetRefreshRunRecord)
        .order_by(DatasetRefreshRunRecord.started_at.desc(), DatasetRefreshRunRecord.run_id.desc())
        .limit(limit)
    ).scalars()

    items = [_to_refresh_run_response(row) for row in rows]
    return RefreshRunsResponse(total=total, limit=limit, items=items)


app.include_router(router)
