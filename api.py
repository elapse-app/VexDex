from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from db import (
    DatasetRefreshRunRecord,
    TeamRecord,
    TeamSeasonSummaryRecord,
    ensure_schema,
    get_engine,
    get_latest_season_id,
)

engine = get_engine()
ensure_schema(engine)

app = FastAPI(
    title="VexDex API",
    version="0.1.0",
    description="Read API for VEX team analytics and refresh status.",
)


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


def get_db() -> Iterator[Session]:
    with Session(engine) as session:
        yield session


DbSession = Annotated[Session, Depends(get_db)]


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


@app.get("/api/v1/teams", response_model=TeamLeaderboardResponse)
def list_current_teams(
    db: DbSession,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> TeamLeaderboardResponse:
    return list_teams_for_season(_require_latest_season_id(db), db, limit=limit, offset=offset)


@app.get("/api/v1/teams/{team_id}", response_model=TeamSeasonResponse)
def get_current_team_by_id(team_id: int, db: DbSession) -> TeamSeasonResponse:
    return get_team_for_season_by_id(_require_latest_season_id(db), team_id, db)


@app.get("/api/v1/teams/by-number/{team_num}", response_model=TeamSeasonResponse)
def get_current_team_by_number(team_num: str, db: DbSession) -> TeamSeasonResponse:
    return get_team_for_season_by_number(_require_latest_season_id(db), team_num, db)


@app.get("/api/v1/seasons", response_model=list[SeasonSummaryResponse])
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


@app.get("/api/v1/seasons/{season_id}/teams", response_model=TeamLeaderboardResponse)
def list_teams_for_season(
    season_id: int,
    db: DbSession,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
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
        .order_by(
            TeamSeasonSummaryRecord.ts_rank.asc(),
            desc(TeamSeasonSummaryRecord.ts_exposed),
            TeamSeasonSummaryRecord.team_num.asc(),
        )
        .offset(offset)
        .limit(limit)
    ).all()

    items = [_to_team_response(row, team) for row, team in rows]
    return TeamLeaderboardResponse(total=total, limit=limit, offset=offset, items=items)


@app.get("/api/v1/seasons/{season_id}/teams/{team_id}", response_model=TeamSeasonResponse)
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


@app.get(
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


@app.get("/api/v1/refresh-runs/latest", response_model=RefreshRunResponse)
def get_latest_refresh_run(db: DbSession) -> RefreshRunResponse:
    row = db.execute(
        select(DatasetRefreshRunRecord)
        .order_by(DatasetRefreshRunRecord.started_at.desc(), DatasetRefreshRunRecord.run_id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="No refresh runs found")
    return _to_refresh_run_response(row)


@app.get("/api/v1/refresh-runs", response_model=RefreshRunsResponse)
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
