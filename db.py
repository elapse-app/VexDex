from __future__ import annotations

from datetime import UTC, datetime
from os import getenv
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    create_engine,
    inspect,
    select,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

if TYPE_CHECKING:
    from team_stats import TeamStats


class Base(DeclarativeBase):
    pass


class TeamStatsRecord(Base):
    __tablename__ = "team_stats"

    team_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_num: Mapped[str] = mapped_column(String(64), default="")
    team_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    grade: Mapped[str] = mapped_column(String(32), default="High School")
    region: Mapped[str | None] = mapped_column(String(255), nullable=True)

    total_matches: Mapped[int] = mapped_column(Integer, default=0)
    total_wins: Mapped[int] = mapped_column(Integer, default=0)
    total_losses: Mapped[int] = mapped_column(Integer, default=0)
    total_draws: Mapped[int] = mapped_column(Integer, default=0)
    total_winrate: Mapped[float] = mapped_column(Float, default=0.0)

    qual_wins: Mapped[int] = mapped_column(Integer, default=0)
    qual_losses: Mapped[int] = mapped_column(Integer, default=0)
    qual_draws: Mapped[int] = mapped_column(Integer, default=0)
    qual_winrate: Mapped[float] = mapped_column(Float, default=0.0)

    elim_wins: Mapped[int] = mapped_column(Integer, default=0)
    elim_losses: Mapped[int] = mapped_column(Integer, default=0)
    elim_draws: Mapped[int] = mapped_column(Integer, default=0)
    elim_winrate: Mapped[float] = mapped_column(Float, default=0.0)

    skills_prog: Mapped[int] = mapped_column(Integer, default=0)
    skills_driver: Mapped[int] = mapped_column(Integer, default=0)
    skills_total: Mapped[int] = mapped_column(Integer, default=0)
    skills_global_rank: Mapped[int] = mapped_column(Integer, default=0)
    skills_region_rank: Mapped[int] = mapped_column(Integer, default=0)

    avg_ap: Mapped[float] = mapped_column(Float, default=0.0)
    avg_awp: Mapped[float] = mapped_column(Float, default=0.0)
    avg_match_wp: Mapped[float] = mapped_column(Float, default=0.0)

    matches_played: Mapped[int] = mapped_column(Integer, default=0)
    opr: Mapped[float] = mapped_column(Float, default=0.0)
    dpr: Mapped[float] = mapped_column(Float, default=0.0)
    ccwm: Mapped[float] = mapped_column(Float, default=0.0)

    ts: Mapped[float] = mapped_column(Float, default=0.0)
    ts_rank: Mapped[int] = mapped_column(Integer, default=0)
    ts_mu: Mapped[float] = mapped_column(Float, default=0.0)
    ts_sigma: Mapped[float] = mapped_column(Float, default=0.0)

    qualed_worlds: Mapped[bool] = mapped_column(Boolean, default=False)
    qualed_regionals: Mapped[bool] = mapped_column(Boolean, default=False)

    unqualed_worlds_skills_global_rank: Mapped[int] = mapped_column(Integer, default=0)
    unqualed_regionals_skills_region_rank: Mapped[int] = mapped_column(Integer, default=0)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class TeamSeasonStatsRecord(Base):
    __tablename__ = "team_season_stats"

    season_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_num: Mapped[str] = mapped_column(String(64), default="")
    team_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    grade: Mapped[str] = mapped_column(String(32), default="High School")
    region: Mapped[str | None] = mapped_column(String(255), nullable=True)

    total_matches: Mapped[int] = mapped_column(Integer, default=0)
    total_wins: Mapped[int] = mapped_column(Integer, default=0)
    total_losses: Mapped[int] = mapped_column(Integer, default=0)
    total_draws: Mapped[int] = mapped_column(Integer, default=0)
    total_winrate: Mapped[float] = mapped_column(Float, default=0.0)

    qual_wins: Mapped[int] = mapped_column(Integer, default=0)
    qual_losses: Mapped[int] = mapped_column(Integer, default=0)
    qual_draws: Mapped[int] = mapped_column(Integer, default=0)
    qual_winrate: Mapped[float] = mapped_column(Float, default=0.0)

    elim_wins: Mapped[int] = mapped_column(Integer, default=0)
    elim_losses: Mapped[int] = mapped_column(Integer, default=0)
    elim_draws: Mapped[int] = mapped_column(Integer, default=0)
    elim_winrate: Mapped[float] = mapped_column(Float, default=0.0)

    skills_prog: Mapped[int] = mapped_column(Integer, default=0)
    skills_driver: Mapped[int] = mapped_column(Integer, default=0)
    skills_total: Mapped[int] = mapped_column(Integer, default=0)
    skills_global_rank: Mapped[int] = mapped_column(Integer, default=0)
    skills_region_rank: Mapped[int] = mapped_column(Integer, default=0)

    avg_ap: Mapped[float] = mapped_column(Float, default=0.0)
    avg_awp: Mapped[float] = mapped_column(Float, default=0.0)
    avg_match_wp: Mapped[float] = mapped_column(Float, default=0.0)

    matches_played: Mapped[int] = mapped_column(Integer, default=0)
    opr: Mapped[float] = mapped_column(Float, default=0.0)
    dpr: Mapped[float] = mapped_column(Float, default=0.0)
    ccwm: Mapped[float] = mapped_column(Float, default=0.0)

    ts: Mapped[float] = mapped_column(Float, default=0.0)
    ts_rank: Mapped[int] = mapped_column(Integer, default=0)
    ts_mu: Mapped[float] = mapped_column(Float, default=0.0)
    ts_sigma: Mapped[float] = mapped_column(Float, default=0.0)

    qualed_worlds: Mapped[bool] = mapped_column(Boolean, default=False)
    qualed_regionals: Mapped[bool] = mapped_column(Boolean, default=False)

    unqualed_worlds_skills_global_rank: Mapped[int] = mapped_column(Integer, default=0)
    unqualed_regionals_skills_region_rank: Mapped[int] = mapped_column(Integer, default=0)

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class ProcessedEventRecord(Base):
    __tablename__ = "processed_events"

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    event_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    processed_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class DatasetRefreshRunRecord(Base):
    __tablename__ = "dataset_refresh_runs"

    run_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    events_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    teams_upserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    dataset_fresh: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


def get_engine() -> Engine:
    db_url = getenv("DATABASE_URL")
    if db_url:
        return create_engine(db_url, future=True, pool_pre_ping=True)

    user = getenv("DB_USER", "")
    password = getenv("DB_PASS", "")
    host = getenv("DB_HOST", "")
    database = getenv("DB_NAME", "")

    if not all([user, password, host, database]):
        raise RuntimeError(
            "Database connection is not configured. "
            "Set DATABASE_URL or all of DB_USER, DB_PASS, DB_HOST, DB_NAME."
        )

    return create_engine(
        f"mssql+pyodbc://{user}:{password}@{host}/{database}?driver=ODBC+Driver+18+for+SQL+Server",
        future=True,
        pool_pre_ping=True,
    )


def ensure_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)

    # Backfill columns for existing processed_events tables created before
    # event_start/event_end tracking existed.
    table_columns = {column["name"] for column in inspect(engine).get_columns("processed_events")}
    dialect_name = engine.dialect.name.lower()
    dt_type = "TIMESTAMP" if dialect_name in {"postgresql", "sqlite"} else "DATETIME"
    alter_statements: list[str] = []
    if "event_start" not in table_columns:
        alter_statements.append(f"ALTER TABLE processed_events ADD event_start {dt_type} NULL")
    if "event_end" not in table_columns:
        alter_statements.append(f"ALTER TABLE processed_events ADD event_end {dt_type} NULL")

    if alter_statements:
        with engine.begin() as conn:
            for statement in alter_statements:
                conn.execute(text(statement))


def upsert_team_stats(engine: Engine, stats: list[TeamStats]) -> None:
    now = datetime.now(UTC)
    with Session(engine) as session:
        for team in stats:
            session.merge(
                TeamStatsRecord(
                    team_id=int(team.team_id),
                    team_num=str(team.team_num),
                    team_name=str(team.team_name) if team.team_name is not None else None,
                    grade=team.grade.value,
                    region=str(team.region) if team.region is not None else None,
                    total_matches=int(team.total_matches),
                    total_wins=int(team.total_wins),
                    total_losses=int(team.total_losses),
                    total_draws=int(team.total_draws),
                    total_winrate=float(team.total_winrate),
                    qual_wins=int(team.qual_wins),
                    qual_losses=int(team.qual_losses),
                    qual_draws=int(team.qual_draws),
                    qual_winrate=float(team.qual_winrate),
                    elim_wins=int(team.elim_wins),
                    elim_losses=int(team.elim_losses),
                    elim_draws=int(team.elim_draws),
                    elim_winrate=float(team.elim_winrate),
                    skills_prog=int(team.skills_prog),
                    skills_driver=int(team.skills_driver),
                    skills_total=int(team.skills_total),
                    skills_global_rank=int(team.skills_global_rank),
                    skills_region_rank=int(team.skills_region_rank),
                    avg_ap=float(team.avg_ap),
                    avg_awp=float(team.avg_awp),
                    avg_match_wp=float(team.avg_match_wp),
                    matches_played=int(team.matches_played),
                    opr=float(team.opr),
                    dpr=float(team.dpr),
                    ccwm=float(team.ccwm),
                    ts=float(team.ts),
                    ts_rank=int(team.ts_rank),
                    ts_mu=float(team.ts_mu),
                    ts_sigma=float(team.ts_sigma),
                    qualed_worlds=bool(team.qualed_worlds),
                    qualed_regionals=bool(team.qualed_regionals),
                    unqualed_worlds_skills_global_rank=int(team.unqualed_worlds_skills_global_rank),
                    unqualed_regionals_skills_region_rank=int(
                        team.unqualed_regionals_skills_region_rank
                    ),
                    updated_at=now,
                )
            )

        session.commit()


def upsert_team_season_stats(engine: Engine, season_id: int, stats: list[TeamStats]) -> None:
    now = datetime.now(UTC)
    with Session(engine) as session:
        for team in stats:
            session.merge(
                TeamSeasonStatsRecord(
                    season_id=season_id,
                    team_id=int(team.team_id),
                    team_num=str(team.team_num),
                    team_name=str(team.team_name) if team.team_name is not None else None,
                    grade=team.grade.value,
                    region=str(team.region) if team.region is not None else None,
                    total_matches=int(team.total_matches),
                    total_wins=int(team.total_wins),
                    total_losses=int(team.total_losses),
                    total_draws=int(team.total_draws),
                    total_winrate=float(team.total_winrate),
                    qual_wins=int(team.qual_wins),
                    qual_losses=int(team.qual_losses),
                    qual_draws=int(team.qual_draws),
                    qual_winrate=float(team.qual_winrate),
                    elim_wins=int(team.elim_wins),
                    elim_losses=int(team.elim_losses),
                    elim_draws=int(team.elim_draws),
                    elim_winrate=float(team.elim_winrate),
                    skills_prog=int(team.skills_prog),
                    skills_driver=int(team.skills_driver),
                    skills_total=int(team.skills_total),
                    skills_global_rank=int(team.skills_global_rank),
                    skills_region_rank=int(team.skills_region_rank),
                    avg_ap=float(team.avg_ap),
                    avg_awp=float(team.avg_awp),
                    avg_match_wp=float(team.avg_match_wp),
                    matches_played=int(team.matches_played),
                    opr=float(team.opr),
                    dpr=float(team.dpr),
                    ccwm=float(team.ccwm),
                    ts=float(team.ts),
                    ts_rank=int(team.ts_rank),
                    ts_mu=float(team.ts_mu),
                    ts_sigma=float(team.ts_sigma),
                    qualed_worlds=bool(team.qualed_worlds),
                    qualed_regionals=bool(team.qualed_regionals),
                    unqualed_worlds_skills_global_rank=int(team.unqualed_worlds_skills_global_rank),
                    unqualed_regionals_skills_region_rank=int(
                        team.unqualed_regionals_skills_region_rank
                    ),
                    updated_at=now,
                )
            )

        session.commit()


def mark_event_processed(
    engine: Engine,
    event_id: int,
    event_start: datetime | None = None,
    event_end: datetime | None = None,
) -> None:
    with Session(engine) as session:
        session.merge(
            ProcessedEventRecord(
                event_id=event_id,
                event_start=event_start,
                event_end=event_end,
                processed_at=datetime.now(UTC),
            )
        )
        session.commit()


def get_processed_event_ids(engine: Engine) -> set[int]:
    with Session(engine) as session:
        rows = session.execute(select(ProcessedEventRecord.event_id)).all()
    return {int(row[0]) for row in rows}


def get_last_updated_event_start(engine: Engine) -> datetime | None:
    with Session(engine) as session:
        return session.execute(
            select(ProcessedEventRecord.event_start)
            .where(ProcessedEventRecord.event_start.is_not(None))
            .order_by(ProcessedEventRecord.processed_at.desc())
            .limit(1)
        ).scalar_one_or_none()


def get_oldest_in_progress_event_start(engine: Engine, now: datetime) -> datetime | None:
    with Session(engine) as session:
        return session.execute(
            select(ProcessedEventRecord.event_start)
            .where(ProcessedEventRecord.event_start.is_not(None))
            .where(ProcessedEventRecord.event_end.is_not(None))
            .where(ProcessedEventRecord.event_end >= now)
            .order_by(ProcessedEventRecord.event_start.asc())
            .limit(1)
        ).scalar_one_or_none()


def get_in_progress_event_ids(engine: Engine, now: datetime) -> set[int]:
    with Session(engine) as session:
        rows = session.execute(
            select(ProcessedEventRecord.event_id)
            .where(ProcessedEventRecord.event_end.is_not(None))
            .where(ProcessedEventRecord.event_end >= now)
        ).all()
    return {int(row[0]) for row in rows}


def start_refresh_run(engine: Engine, season_id: int) -> int:
    with Session(engine) as session:
        row = DatasetRefreshRunRecord(
            season_id=season_id,
            status="running",
            dataset_fresh=False,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return int(row.run_id)


def complete_refresh_run(
    engine: Engine,
    run_id: int,
    status: str,
    events_processed: int,
    teams_upserted: int,
    error_message: str | None = None,
) -> None:
    with Session(engine) as session:
        row = session.get(DatasetRefreshRunRecord, run_id)
        if row is None:
            raise RuntimeError(f"Refresh run {run_id} was not found.")

        row.status = status
        row.events_processed = events_processed
        row.teams_upserted = teams_upserted
        row.error_message = error_message
        row.completed_at = datetime.now(UTC)
        row.dataset_fresh = status == "succeeded"
        session.commit()


