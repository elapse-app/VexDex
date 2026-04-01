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
    TeamSeasonStatsRecord,
    TeamStatsRecord,
    ensure_schema,
    get_engine,
)

engine = get_engine()
ensure_schema(engine)

app = FastAPI(
    title="VexDex API",
    version="0.1.0",
    description="Read API for VEX team analytics and refresh status.",
)


class TeamStatsResponse(BaseModel):
    season_id: int | None = None
    team_id: int
    team_num: str
    team_name: str | None
    grade: str
    region: str | None
    matches_played: int
    opr: float
    dpr: float
    ccwm: float
    ts: float
    ts_rank: int
    ts_mu: float
    ts_sigma: float
    updated_at: datetime


class TeamLeaderboardResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[TeamStatsResponse]


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


def _to_team_response(row: TeamStatsRecord, season_id: int | None = None) -> TeamStatsResponse:
    return TeamStatsResponse(
        season_id=season_id,
        team_id=row.team_id,
        team_num=row.team_num,
        team_name=row.team_name,
        grade=row.grade,
        region=row.region,
        matches_played=row.matches_played,
        opr=row.opr,
        dpr=row.dpr,
        ccwm=row.ccwm,
        ts=row.ts,
        ts_rank=row.ts_rank,
        ts_mu=row.ts_mu,
        ts_sigma=row.ts_sigma,
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


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/teams", response_model=TeamLeaderboardResponse)
def list_current_teams(
    db: DbSession,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> TeamLeaderboardResponse:
    total = db.execute(select(func.count()).select_from(TeamStatsRecord)).scalar_one()

    rows = db.execute(
        select(TeamStatsRecord)
        .order_by(
            TeamStatsRecord.ts_rank.asc(),
            desc(TeamStatsRecord.ts),
            TeamStatsRecord.team_num.asc(),
        )
        .offset(offset)
        .limit(limit)
    ).scalars()

    items = [_to_team_response(row, season_id=None) for row in rows]
    return TeamLeaderboardResponse(total=total, limit=limit, offset=offset, items=items)


@app.get("/api/v1/teams/{team_id}", response_model=TeamStatsResponse)
def get_current_team_by_id(team_id: int, db: DbSession) -> TeamStatsResponse:
    row = db.get(TeamStatsRecord, team_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Team not found")
    return _to_team_response(row, season_id=None)


@app.get("/api/v1/teams/by-number/{team_num}", response_model=TeamStatsResponse)
def get_current_team_by_number(team_num: str, db: DbSession) -> TeamStatsResponse:
    row = db.execute(
        select(TeamStatsRecord).where(TeamStatsRecord.team_num == team_num)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Team not found")
    return _to_team_response(row, season_id=None)


@app.get("/api/v1/seasons", response_model=list[SeasonSummaryResponse])
def list_historical_seasons(db: DbSession) -> list[SeasonSummaryResponse]:
    rows = db.execute(
        select(
            TeamSeasonStatsRecord.season_id,
            func.count().label("teams"),
            func.max(TeamSeasonStatsRecord.updated_at).label("last_updated"),
        )
        .group_by(TeamSeasonStatsRecord.season_id)
        .order_by(TeamSeasonStatsRecord.season_id.desc())
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
        .select_from(TeamSeasonStatsRecord)
        .where(TeamSeasonStatsRecord.season_id == season_id)
    ).scalar_one()

    rows = db.execute(
        select(TeamSeasonStatsRecord)
        .where(TeamSeasonStatsRecord.season_id == season_id)
        .order_by(
            TeamSeasonStatsRecord.ts_rank.asc(),
            desc(TeamSeasonStatsRecord.ts),
            TeamSeasonStatsRecord.team_num.asc(),
        )
        .offset(offset)
        .limit(limit)
    ).scalars()

    items = [_to_team_response(row, season_id=season_id) for row in rows]
    return TeamLeaderboardResponse(total=total, limit=limit, offset=offset, items=items)


@app.get("/api/v1/seasons/{season_id}/teams/{team_id}", response_model=TeamStatsResponse)
def get_team_for_season_by_id(season_id: int, team_id: int, db: DbSession) -> TeamStatsResponse:
    row = db.execute(
        select(TeamSeasonStatsRecord)
        .where(TeamSeasonStatsRecord.season_id == season_id)
        .where(TeamSeasonStatsRecord.team_id == team_id)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Team not found for this season")
    return _to_team_response(row, season_id=season_id)


@app.get(
    "/api/v1/seasons/{season_id}/teams/by-number/{team_num}",
    response_model=TeamStatsResponse,
)
def get_team_for_season_by_number(
    season_id: int,
    team_num: str,
    db: DbSession,
) -> TeamStatsResponse:
    row = db.execute(
        select(TeamSeasonStatsRecord)
        .where(TeamSeasonStatsRecord.season_id == season_id)
        .where(TeamSeasonStatsRecord.team_num == team_num)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Team not found for this season")
    return _to_team_response(row, season_id=season_id)


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
