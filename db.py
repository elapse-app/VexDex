from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from os import getenv
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

if TYPE_CHECKING:
    from event import Event
    from team_profile import TeamProfile
    from team_stats import TeamStats


class Base(DeclarativeBase):
    pass


class TeamRecord(Base):
    """Team identity. team_num is the API's team number string (e.g. "12141A").
    team_name/grade/region come from a one-time /teams/{id} profile fetch —
    null until that's happened for this team."""

    __tablename__ = "teams"

    team_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_num: Mapped[str] = mapped_column(String(64))
    team_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    grade: Mapped[str | None] = mapped_column(String(32), nullable=True)
    region: Mapped[str | None] = mapped_column(String(255), nullable=True)
    profile_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class EventRecord(Base):
    """Event identity plus ingestion checkpoint (processed_at, event_start/end)."""

    __tablename__ = "events"

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    season_id: Mapped[int] = mapped_column(Integer)
    event_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    event_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class TeamEventResultRecord(Base):
    """One immutable row per team per event. Never updated after insert."""

    __tablename__ = "team_event_results"

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    season_id: Mapped[int] = mapped_column(Integer)

    total_matches: Mapped[int] = mapped_column(Integer, default=0)
    total_wins: Mapped[int] = mapped_column(Integer, default=0)
    total_losses: Mapped[int] = mapped_column(Integer, default=0)
    total_draws: Mapped[int] = mapped_column(Integer, default=0)
    total_winrate: Mapped[float] = mapped_column(Float, default=0.0)

    qual_matches: Mapped[int] = mapped_column(Integer, default=0)
    qual_wins: Mapped[int] = mapped_column(Integer, default=0)
    qual_losses: Mapped[int] = mapped_column(Integer, default=0)
    qual_draws: Mapped[int] = mapped_column(Integer, default=0)
    qual_winrate: Mapped[float] = mapped_column(Float, default=0.0)

    elim_matches: Mapped[int] = mapped_column(Integer, default=0)
    elim_wins: Mapped[int] = mapped_column(Integer, default=0)
    elim_losses: Mapped[int] = mapped_column(Integer, default=0)
    elim_draws: Mapped[int] = mapped_column(Integer, default=0)
    elim_winrate: Mapped[float] = mapped_column(Float, default=0.0)

    # Cumulative ranking-tiebreaker points at this event (qual-match scope):
    # win points, autonomous points, strength-of-schedule points.
    wp: Mapped[int] = mapped_column(Integer, default=0)
    ap: Mapped[int] = mapped_column(Integer, default=0)
    sp: Mapped[int] = mapped_column(Integer, default=0)
    avg_ap: Mapped[float] = mapped_column(Float, default=0.0)
    avg_wp: Mapped[float] = mapped_column(Float, default=0.0)
    # AWP isn't a distinct API field — it's estimated from the official VRC/
    # V5RC point rules: 2 WP per win, 1 per tie, +1 WP bonus per AWP earned.
    avg_awp: Mapped[float] = mapped_column(Float, default=0.0)
    average_match_score: Mapped[float] = mapped_column(Float, default=0.0)
    high_score: Mapped[int] = mapped_column(Integer, default=0)

    opr: Mapped[float] = mapped_column(Float, default=0.0)
    dpr: Mapped[float] = mapped_column(Float, default=0.0)
    ccwm: Mapped[float] = mapped_column(Float, default=0.0)

    # Strength of schedule (avg opponent OPR this event) and field-strength
    # z-score (this team's OPR vs. this event's field), both computed from
    # this event's own OPR values so they're comparable across events.
    sos: Mapped[float] = mapped_column(Float, default=0.0)
    field_strength_z: Mapped[float] = mapped_column(Float, default=0.0)

    ts_mu: Mapped[float] = mapped_column(Float, default=0.0)
    ts_sigma: Mapped[float] = mapped_column(Float, default=0.0)
    ts_exposed: Mapped[float] = mapped_column(Float, default=0.0)
    ts_rank: Mapped[int] = mapped_column(Integer, default=0)

    skills_driver: Mapped[int | None] = mapped_column(Integer, nullable=True)
    skills_prog: Mapped[int | None] = mapped_column(Integer, nullable=True)
    skills_total: Mapped[int | None] = mapped_column(Integer, nullable=True)

    qualed_worlds: Mapped[bool] = mapped_column(Boolean, default=False)
    qualed_regionals: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class TeamAwardRecord(Base):
    """One row per award a team won at an event. qualed_worlds/qualed_regionals
    on team_event_results are derived from this — this table is the actual
    history (what award, at what event)."""

    __tablename__ = "team_awards"

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), primary_key=True)
    season_id: Mapped[int] = mapped_column(Integer)
    qualifications: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class TeamSeasonSummaryRecord(Base):
    """Derived from team_event_results (+ teams for region). Safe to drop and
    rebuild at any time."""

    __tablename__ = "team_season_summary"

    season_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    team_num: Mapped[str] = mapped_column(String(64))

    events_count: Mapped[int] = mapped_column(Integer, default=0)
    matches_played: Mapped[int] = mapped_column(Integer, default=0)

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

    avg_ap: Mapped[float] = mapped_column(Float, default=0.0)
    avg_wp: Mapped[float] = mapped_column(Float, default=0.0)
    avg_awp: Mapped[float] = mapped_column(Float, default=0.0)

    opr_avg: Mapped[float] = mapped_column(Float, default=0.0)
    opr_best: Mapped[float] = mapped_column(Float, default=0.0)
    dpr_avg: Mapped[float] = mapped_column(Float, default=0.0)
    dpr_best: Mapped[float] = mapped_column(Float, default=0.0)
    ccwm_avg: Mapped[float] = mapped_column(Float, default=0.0)
    ccwm_best: Mapped[float] = mapped_column(Float, default=0.0)

    sos_avg: Mapped[float] = mapped_column(Float, default=0.0)
    field_strength_z_avg: Mapped[float] = mapped_column(Float, default=0.0)

    # Percentile rank (0-100) within this season: 100 = best. Computed once
    # every team in the season has been aggregated, so it's stable across a
    # rebuild as long as the same set of teams goes in.
    percentile_ccwm: Mapped[float | None] = mapped_column(Float, nullable=True)
    percentile_ts: Mapped[float | None] = mapped_column(Float, nullable=True)

    # v1 alliance pick-list score: 50% CCWM percentile + 30% skills percentile
    # (neutral 50 if no skills data) + 20% AWP-rate percentile. Weights are a
    # first-pass judgment call, not derived from data — tune freely.
    pick_list_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # TrueSkill is a running belief state, not a quantity to average — these
    # are carried over from the team's most recently processed event.
    ts_mu: Mapped[float] = mapped_column(Float, default=0.0)
    ts_sigma: Mapped[float] = mapped_column(Float, default=0.0)
    ts_exposed: Mapped[float] = mapped_column(Float, default=0.0)
    ts_rank: Mapped[int] = mapped_column(Integer, default=0)

    # Season-best skills performance: the single event where driver+programming
    # combined was highest (VEX's own skills ranking convention — not summed
    # or maxed independently across events).
    skills_driver: Mapped[int | None] = mapped_column(Integer, nullable=True)
    skills_prog: Mapped[int | None] = mapped_column(Integer, nullable=True)
    skills_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    skills_global_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    skills_region_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unqualed_worlds_skills_global_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unqualed_regionals_skills_region_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)

    qualed_worlds: Mapped[bool] = mapped_column(Boolean, default=False)
    qualed_regionals: Mapped[bool] = mapped_column(Boolean, default=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class DatasetRefreshRunRecord(Base):
    __tablename__ = "dataset_refresh_runs"

    run_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    season_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    events_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    teams_upserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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
        f"postgresql+psycopg://{user}:{password}@{host}/{database}",
        future=True,
        pool_pre_ping=True,
    )


def ensure_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def record_event_results(engine: Engine, event: Event, results: list[TeamStats]) -> None:
    """Persist one immutable team_event_results row per team for this event,
    plus the event and team identity rows. Never mutates a prior event's rows."""
    now = datetime.now(UTC)
    with Session(engine) as session:
        session.merge(
            EventRecord(
                event_id=event.id,
                sku=event.sku,
                name=event.name,
                season_id=event.season_id,
                event_start=event.start,
                event_end=event.end,
                processed_at=now,
            )
        )

        for team in results:
            session.merge(TeamRecord(team_id=team.team_id, team_num=team.team_num, updated_at=now))
            session.merge(
                TeamEventResultRecord(
                    event_id=event.id,
                    team_id=team.team_id,
                    season_id=event.season_id,
                    total_matches=team.total_matches,
                    total_wins=team.total_wins,
                    total_losses=team.total_losses,
                    total_draws=team.total_draws,
                    total_winrate=team.total_winrate,
                    qual_matches=team.qual_matches,
                    qual_wins=team.qual_wins,
                    qual_losses=team.qual_losses,
                    qual_draws=team.qual_draws,
                    qual_winrate=team.qual_winrate,
                    elim_matches=team.elim_matches,
                    elim_wins=team.elim_wins,
                    elim_losses=team.elim_losses,
                    elim_draws=team.elim_draws,
                    elim_winrate=team.elim_winrate,
                    wp=team.wp,
                    ap=team.ap,
                    sp=team.sp,
                    avg_ap=team.avg_ap,
                    avg_wp=team.avg_wp,
                    avg_awp=team.avg_awp,
                    average_match_score=team.average_match_score,
                    high_score=team.high_score,
                    opr=team.opr,
                    dpr=team.dpr,
                    ccwm=team.ccwm,
                    sos=team.sos,
                    field_strength_z=team.field_strength_z,
                    ts_mu=team.ts_mu,
                    ts_sigma=team.ts_sigma,
                    ts_exposed=team.ts,
                    ts_rank=team.ts_rank,
                    skills_driver=team.skills_driver,
                    skills_prog=team.skills_prog,
                    skills_total=team.skills_total,
                    qualed_worlds=team.qualed_worlds,
                    qualed_regionals=team.qualed_regionals,
                    created_at=now,
                )
            )
            for title, qualifications in team.awards:
                session.merge(
                    TeamAwardRecord(
                        event_id=event.id,
                        team_id=team.team_id,
                        title=title,
                        season_id=event.season_id,
                        qualifications=qualifications,
                        created_at=now,
                    )
                )

        session.commit()


def get_teams_missing_profile(engine: Engine, team_ids: set[int]) -> set[int]:
    """team_ids that don't yet have a /teams/{id} profile fetched."""
    if not team_ids:
        return set()
    with Session(engine) as session:
        have_profile = session.execute(
            select(TeamRecord.team_id)
            .where(TeamRecord.team_id.in_(team_ids))
            .where(TeamRecord.profile_fetched_at.is_not(None))
        ).all()
    return team_ids - {int(row[0]) for row in have_profile}


def record_team_profiles(engine: Engine, profiles: list[TeamProfile]) -> None:
    now = datetime.now(UTC)
    with Session(engine) as session:
        for profile in profiles:
            session.merge(
                TeamRecord(
                    team_id=profile.team_id,
                    team_num=profile.team_num,
                    team_name=profile.team_name,
                    grade=profile.grade,
                    region=profile.region,
                    profile_fetched_at=now,
                    updated_at=now,
                )
            )
        session.commit()


def _win_rate(wins: int, losses: int, draws: int) -> float:
    total = wins + losses + draws
    if total == 0:
        return 0.0
    return (wins + 0.5 * draws) / total


def refresh_team_season_summary(engine: Engine, season_id: int) -> int:
    """Rebuild team_season_summary for a season from team_event_results (plus
    teams for region). Purely derived — safe to call repeatedly. Returns the
    number of teams summarized."""
    now = datetime.now(UTC)
    with Session(engine) as session:
        rows = session.execute(
            select(TeamEventResultRecord, TeamRecord.team_num, TeamRecord.region)
            .join(TeamRecord, TeamRecord.team_id == TeamEventResultRecord.team_id)
            .where(TeamEventResultRecord.season_id == season_id)
            .order_by(TeamEventResultRecord.created_at.asc())
        ).all()

        by_team: dict[int, list[tuple[TeamEventResultRecord, str, str | None]]] = defaultdict(list)
        for result, team_num, region in rows:
            by_team[result.team_id].append((result, team_num, region))

        summaries: dict[int, TeamSeasonSummaryRecord] = {}
        skills_totals: dict[int, int] = {}
        regions: dict[int, str | None] = {}

        for team_id, team_rows in by_team.items():
            results = [r for r, _, _ in team_rows]
            team_num = team_rows[-1][1]
            region = team_rows[-1][2]
            latest = team_rows[-1][0]

            n = len(results)
            best_skills_row = max(
                (r for r in results if r.skills_total is not None),
                key=lambda r: r.skills_total,
                default=None,
            )
            total_qual_matches = sum(r.qual_matches for r in results)
            total_ap = sum(r.ap for r in results)
            total_wp = sum(r.wp for r in results)
            total_qual_wins = sum(r.qual_wins for r in results)
            total_qual_draws = sum(r.qual_draws for r in results)

            summaries[team_id] = TeamSeasonSummaryRecord(
                season_id=season_id,
                team_id=team_id,
                team_num=team_num,
                events_count=n,
                matches_played=sum(r.total_matches for r in results),
                total_wins=sum(r.total_wins for r in results),
                total_losses=sum(r.total_losses for r in results),
                total_draws=sum(r.total_draws for r in results),
                total_winrate=_win_rate(
                    sum(r.total_wins for r in results),
                    sum(r.total_losses for r in results),
                    sum(r.total_draws for r in results),
                ),
                qual_wins=total_qual_wins,
                qual_losses=sum(r.qual_losses for r in results),
                qual_draws=total_qual_draws,
                qual_winrate=_win_rate(
                    total_qual_wins, sum(r.qual_losses for r in results), total_qual_draws
                ),
                elim_wins=sum(r.elim_wins for r in results),
                elim_losses=sum(r.elim_losses for r in results),
                elim_draws=sum(r.elim_draws for r in results),
                elim_winrate=_win_rate(
                    sum(r.elim_wins for r in results),
                    sum(r.elim_losses for r in results),
                    sum(r.elim_draws for r in results),
                ),
                avg_ap=total_ap / total_qual_matches if total_qual_matches else 0.0,
                avg_wp=total_wp / total_qual_matches if total_qual_matches else 0.0,
                avg_awp=(total_wp - 2 * total_qual_wins - total_qual_draws) / total_qual_matches
                if total_qual_matches
                else 0.0,
                opr_avg=sum(r.opr for r in results) / n,
                opr_best=max(r.opr for r in results),
                dpr_avg=sum(r.dpr for r in results) / n,
                dpr_best=min(r.dpr for r in results),  # lower DPR is better defense
                ccwm_avg=sum(r.ccwm for r in results) / n,
                ccwm_best=max(r.ccwm for r in results),
                sos_avg=sum(r.sos for r in results) / n,
                field_strength_z_avg=sum(r.field_strength_z for r in results) / n,
                ts_mu=latest.ts_mu,
                ts_sigma=latest.ts_sigma,
                ts_exposed=latest.ts_exposed,
                ts_rank=latest.ts_rank,
                skills_driver=best_skills_row.skills_driver if best_skills_row else None,
                skills_prog=best_skills_row.skills_prog if best_skills_row else None,
                skills_total=best_skills_row.skills_total if best_skills_row else None,
                qualed_worlds=any(r.qualed_worlds for r in results),
                qualed_regionals=any(r.qualed_regionals for r in results),
                updated_at=now,
            )
            if best_skills_row is not None:
                skills_totals[team_id] = best_skills_row.skills_total
            regions[team_id] = region

        _assign_skills_ranks(summaries, skills_totals, regions)
        _assign_percentiles_and_pick_list(summaries)

        for summary in summaries.values():
            session.merge(summary)

        session.commit()
        return len(summaries)


def _assign_skills_ranks(
    summaries: dict[int, TeamSeasonSummaryRecord],
    skills_totals: dict[int, int],
    regions: dict[int, str | None],
) -> None:
    """Rank teams by season-best combined skills score: globally, by region,
    and again excluding teams that already have a qualifying award (so a team
    can see where they'd stand if the already-qualified teams took their
    berths and stepped out of contention)."""

    def ranked(team_ids: list[int]) -> dict[int, int]:
        ordered = sorted(team_ids, key=lambda t: (-skills_totals[t], summaries[t].team_num))
        return {team_id: i + 1 for i, team_id in enumerate(ordered)}

    all_teams = list(skills_totals)
    global_ranks = ranked(all_teams)

    by_region: dict[str, list[int]] = defaultdict(list)
    for team_id in all_teams:
        region = regions.get(team_id)
        if region:
            by_region[region].append(team_id)
    region_ranks: dict[int, int] = {}
    for region_teams in by_region.values():
        region_ranks.update(ranked(region_teams))

    unqualed_worlds_teams = [t for t in all_teams if not summaries[t].qualed_worlds]
    unqualed_worlds_ranks = ranked(unqualed_worlds_teams)

    unqualed_regionals_region_ranks: dict[int, int] = {}
    for region_teams in by_region.values():
        unqualed_teams = [t for t in region_teams if not summaries[t].qualed_regionals]
        unqualed_regionals_region_ranks.update(ranked(unqualed_teams))

    for team_id in all_teams:
        summaries[team_id].skills_global_rank = global_ranks.get(team_id)
        summaries[team_id].skills_region_rank = region_ranks.get(team_id)
        summaries[team_id].unqualed_worlds_skills_global_rank = unqualed_worlds_ranks.get(team_id)
        summaries[team_id].unqualed_regionals_skills_region_rank = (
            unqualed_regionals_region_ranks.get(team_id)
        )


def _percentiles(values: dict[int, float]) -> dict[int, float]:
    """0-100 percentile rank within the given team_id -> value map. 100 is
    the best (highest) value; ties share the same percentile."""
    n = len(values)
    if n == 0:
        return {}
    if n == 1:
        return {next(iter(values)): 100.0}

    ordered = sorted(values.items(), key=lambda item: item[1], reverse=True)
    percentiles: dict[int, float] = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and ordered[j + 1][1] == ordered[i][1]:
            j += 1
        # Every team tied at this value gets the percentile of the best
        # (lowest) rank among them, matching how ties read intuitively.
        pct = 100.0 * (n - 1 - i) / (n - 1)
        for k in range(i, j + 1):
            percentiles[ordered[k][0]] = pct
        i = j + 1
    return percentiles


PICK_LIST_WEIGHTS = {"ccwm": 0.5, "skills": 0.3, "awp": 0.2}


def _assign_percentiles_and_pick_list(summaries: dict[int, TeamSeasonSummaryRecord]) -> None:
    """Season-wide percentile ranks plus a v1 alliance pick-list composite
    score. All percentiles are computed across every team summarized this
    call, so they're only meaningful relative to teams processed together."""
    ccwm_pct = _percentiles({t: s.ccwm_avg for t, s in summaries.items()})
    ts_pct = _percentiles({t: s.ts_exposed for t, s in summaries.items()})
    skills_pct = _percentiles(
        {t: s.skills_total for t, s in summaries.items() if s.skills_total is not None}
    )
    awp_pct = _percentiles({t: s.avg_awp for t, s in summaries.items()})

    for team_id, summary in summaries.items():
        summary.percentile_ccwm = ccwm_pct.get(team_id)
        summary.percentile_ts = ts_pct.get(team_id)

        # A team with no skills data isn't penalized for missing data — it's
        # simply left out of that component (weight redistributed to CCWM).
        skills_component = skills_pct.get(team_id)
        if skills_component is None:
            weight_ccwm = PICK_LIST_WEIGHTS["ccwm"] + PICK_LIST_WEIGHTS["skills"]
            summary.pick_list_score = (
                weight_ccwm * ccwm_pct[team_id] + PICK_LIST_WEIGHTS["awp"] * awp_pct[team_id]
            )
        else:
            summary.pick_list_score = (
                PICK_LIST_WEIGHTS["ccwm"] * ccwm_pct[team_id]
                + PICK_LIST_WEIGHTS["skills"] * skills_component
                + PICK_LIST_WEIGHTS["awp"] * awp_pct[team_id]
            )


def get_processed_event_ids(engine: Engine) -> set[int]:
    with Session(engine) as session:
        rows = session.execute(select(EventRecord.event_id)).all()
    return {int(row[0]) for row in rows}


def get_last_updated_event_start(engine: Engine) -> datetime | None:
    with Session(engine) as session:
        return session.execute(
            select(EventRecord.event_start).order_by(EventRecord.processed_at.desc()).limit(1)
        ).scalar_one_or_none()


def get_oldest_in_progress_event_start(engine: Engine, now: datetime) -> datetime | None:
    with Session(engine) as session:
        return session.execute(
            select(EventRecord.event_start)
            .where(EventRecord.event_end >= now)
            .order_by(EventRecord.event_start.asc())
            .limit(1)
        ).scalar_one_or_none()


def get_in_progress_event_ids(engine: Engine, now: datetime) -> set[int]:
    with Session(engine) as session:
        rows = session.execute(select(EventRecord.event_id).where(EventRecord.event_end >= now)).all()
    return {int(row[0]) for row in rows}


def get_latest_season_id(engine: Engine) -> int | None:
    with Session(engine) as session:
        return session.execute(
            select(TeamSeasonSummaryRecord.season_id)
            .order_by(TeamSeasonSummaryRecord.season_id.desc())
            .limit(1)
        ).scalar_one_or_none()


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
