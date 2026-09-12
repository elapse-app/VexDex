import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

import db
from event import Event
from team_stats import TeamStats


def _as_utc(value: datetime) -> datetime:
    # SQLite has no native timestamptz type, so DateTime(timezone=True) round
    # -trips as naive there even though Postgres preserves tzinfo correctly.
    # Tests only need the instant to match, not the tzinfo object identity.
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


@pytest.fixture
def engine(monkeypatch):
    # Defaults to a fresh in-memory sqlite DB per test. CI also runs this
    # file against a real Postgres service via TEST_DATABASE_URL, since
    # sqlite silently diverges from Postgres on things like tz-aware columns.
    db_url = os.getenv("TEST_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("DATABASE_URL", db_url)
    eng = db.get_engine()
    db.ensure_schema(eng)
    try:
        yield eng
    finally:
        db.Base.metadata.drop_all(eng)


def _event(event_id=1, season_id=190, start=None, end=None) -> Event:
    start = start or datetime(2026, 1, 10, 9, 0, 0, tzinfo=UTC)
    end = end or datetime(2026, 1, 10, 18, 0, 0, tzinfo=UTC)
    return Event(
        id=event_id,
        sku=f"RE-V5RC-26-{event_id:04d}",
        name=f"Test Event {event_id}",
        start=start,
        end=end,
        season_id=season_id,
        divisions_id=[1],
    )


def test_record_event_results_writes_event_team_and_result_rows(engine):
    event = _event()
    results = [
        TeamStats(team_id=1, team_num="100A", total_matches=3, qual_matches=3, opr=10.0, dpr=5.0, ccwm=5.0),
        TeamStats(team_id=2, team_num="200B", total_matches=3, qual_matches=3, opr=8.0, dpr=6.0, ccwm=2.0),
    ]

    db.record_event_results(engine, event, results)

    assert db.get_processed_event_ids(engine) == {event.id}
    assert _as_utc(db.get_last_updated_event_start(engine)) == event.start


def test_record_event_results_is_idempotent_on_rerun(engine):
    event = _event()
    results = [TeamStats(team_id=1, team_num="100A", total_matches=3, qual_matches=3, opr=10.0, dpr=5.0, ccwm=5.0)]

    db.record_event_results(engine, event, results)
    db.record_event_results(engine, event, results)

    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    with Session(engine) as session:
        count = session.execute(
            select(func.count()).select_from(db.TeamEventResultRecord)
        ).scalar_one()
    assert count == 1


def test_refresh_team_season_summary_aggregates_across_events(engine):
    season_id = 190
    event_1 = _event(event_id=1, season_id=season_id, start=datetime(2026, 1, 1, tzinfo=UTC))
    event_2 = _event(event_id=2, season_id=season_id, start=datetime(2026, 1, 8, tzinfo=UTC))

    db.record_event_results(
        engine,
        event_1,
        [TeamStats(team_id=1, team_num="100A", total_matches=4, qual_matches=4, opr=10.0, dpr=6.0, ccwm=4.0,
                    ts_mu=26.0, ts_sigma=7.0, ts=15.0, ts_rank=2)],
    )
    db.record_event_results(
        engine,
        event_2,
        [TeamStats(team_id=1, team_num="100A", total_matches=6, qual_matches=6, opr=20.0, dpr=2.0, ccwm=18.0,
                    ts_mu=30.0, ts_sigma=5.0, ts=20.0, ts_rank=1)],
    )

    teams_summarized = db.refresh_team_season_summary(engine, season_id)
    assert teams_summarized == 1

    from sqlalchemy.orm import Session

    with Session(engine) as session:
        row = session.get(db.TeamSeasonSummaryRecord, {"season_id": season_id, "team_id": 1})

    assert row is not None
    assert row.events_count == 2
    assert row.matches_played == 10
    assert row.opr_avg == pytest.approx(15.0)
    assert row.opr_best == pytest.approx(20.0)
    assert row.dpr_avg == pytest.approx(4.0)
    assert row.dpr_best == pytest.approx(2.0)  # lower DPR is better defense
    # TrueSkill reflects the most recently recorded event, not an average.
    assert row.ts_mu == pytest.approx(30.0)
    assert row.ts_rank == 1


def test_get_latest_season_id_reflects_summarized_seasons(engine):
    assert db.get_latest_season_id(engine) is None

    db.record_event_results(
        engine,
        _event(event_id=1, season_id=190),
        [TeamStats(team_id=1, team_num="100A", total_matches=1, qual_matches=1, opr=1.0, dpr=1.0, ccwm=0.0)],
    )
    db.refresh_team_season_summary(engine, 190)
    assert db.get_latest_season_id(engine) == 190

    db.record_event_results(
        engine,
        _event(event_id=2, season_id=197),
        [TeamStats(team_id=1, team_num="100A", total_matches=1, qual_matches=1, opr=1.0, dpr=1.0, ccwm=0.0)],
    )
    db.refresh_team_season_summary(engine, 197)
    assert db.get_latest_season_id(engine) == 197


def test_refresh_team_season_summary_computes_skills_and_qualification_ranks(engine):
    from team_profile import TeamProfile

    season_id = 190
    event = _event(event_id=1, season_id=season_id)

    # Team 1: best combined skills score, already qualed for worlds.
    team_1 = TeamStats(team_id=1, team_num="100A", total_matches=1, qual_matches=1)
    team_1.skills_driver, team_1.skills_prog = 40, 20  # total 60
    team_1.awards = [("Excellence Award", ["World Championship"])]

    # Team 2: lower skills score, no qualification. Lower TrueSkill than team 3.
    team_2 = TeamStats(team_id=2, team_num="200A", total_matches=1, qual_matches=1)
    team_2.skills_driver, team_2.skills_prog = 30, 10  # total 40
    team_2.ts = 15.0

    # Team 3: same region as team 2, higher skills than team 2 but no quals.
    # Higher TrueSkill than team 2, so region_ts_rank should invert their
    # skills_region_rank ordering.
    team_3 = TeamStats(team_id=3, team_num="300A", total_matches=1, qual_matches=1)
    team_3.skills_driver, team_3.skills_prog = 35, 10  # total 45
    team_3.ts = 20.0

    db.record_event_results(engine, event, [team_1, team_2, team_3])
    db.record_team_profiles(
        engine,
        [
            TeamProfile(team_id=1, team_num="100A", team_name="A", grade="High School", region="CA"),
            TeamProfile(team_id=2, team_num="200A", team_name="B", grade="High School", region="TX"),
            TeamProfile(team_id=3, team_num="300A", team_name="C", grade="High School", region="TX"),
        ],
    )

    db.refresh_team_season_summary(engine, season_id)

    from sqlalchemy.orm import Session

    with Session(engine) as session:
        rows = {
            r.team_id: r
            for r in session.execute(
                select(db.TeamSeasonSummaryRecord).where(db.TeamSeasonSummaryRecord.season_id == season_id)
            ).scalars()
        }

    assert rows[1].skills_total == 60 and rows[1].skills_global_rank == 1
    assert rows[3].skills_total == 45 and rows[2].skills_total == 40
    # Global rank: 1 (team 1, 60) > 3 (team 3, 45) > 2 (team 2, 40).
    assert rows[3].skills_global_rank == 2
    assert rows[2].skills_global_rank == 3

    # Region rank within TX: team 3 (45) beats team 2 (40).
    assert rows[3].skills_region_rank == 1
    assert rows[2].skills_region_rank == 2

    # Region TrueSkill rank within TX: team 3 (ts=20.0) beats team 2 (ts=15.0)
    # — same ordering here, but computed independently from skills_region_rank.
    assert rows[3].region_ts_rank == 1
    assert rows[2].region_ts_rank == 2
    # Team 1 is alone in region CA, so it's rank 1 within its own region.
    assert rows[1].region_ts_rank == 1

    # Qualification flags.
    assert rows[1].qualed_worlds is True
    assert rows[2].qualed_worlds is False and rows[2].qualed_regionals is False

    # Excluding already-qualified team 1, team 3 becomes global rank 1 among
    # the not-yet-qualified. Team 1 itself gets no "unqualed" rank at all.
    assert rows[3].unqualed_worlds_skills_global_rank == 1
    assert rows[2].unqualed_worlds_skills_global_rank == 2
    assert rows[1].unqualed_worlds_skills_global_rank is None


def test_percentiles_pure_function():
    # Best value -> 100th percentile, worst -> 0th, ties share a percentile.
    pcts = db._percentiles({1: 30.0, 2: 20.0, 3: 20.0, 4: 10.0})

    assert pcts[1] == pytest.approx(100.0)
    assert pcts[4] == pytest.approx(0.0)
    assert pcts[2] == pytest.approx(pcts[3])
    assert 0.0 < pcts[2] < 100.0


def test_percentiles_single_team_is_100():
    assert db._percentiles({1: 5.0}) == {1: 100.0}


def test_refresh_team_season_summary_computes_percentiles_and_pick_list(engine):
    season_id = 190
    # Three teams, distinct CCWM, only team 1 has skills data.
    db.record_event_results(
        engine,
        _event(event_id=1, season_id=season_id),
        [
            TeamStats(team_id=1, team_num="1A", total_matches=1, qual_matches=1,
                      opr=30.0, dpr=0.0, ccwm=30.0, wp=4, qual_wins=2,
                      skills_driver=20, skills_prog=10),
            TeamStats(team_id=2, team_num="2A", total_matches=1, qual_matches=1,
                      opr=20.0, dpr=0.0, ccwm=20.0, wp=4, qual_wins=2),
            TeamStats(team_id=3, team_num="3A", total_matches=1, qual_matches=1,
                      opr=10.0, dpr=0.0, ccwm=10.0, wp=4, qual_wins=2),
        ],
    )

    db.refresh_team_season_summary(engine, season_id)

    from sqlalchemy.orm import Session

    with Session(engine) as session:
        rows = {
            r.team_id: r
            for r in session.execute(
                select(db.TeamSeasonSummaryRecord).where(db.TeamSeasonSummaryRecord.season_id == season_id)
            ).scalars()
        }

    # Best CCWM -> 100th percentile, worst -> 0th.
    assert rows[1].percentile_ccwm == pytest.approx(100.0)
    assert rows[3].percentile_ccwm == pytest.approx(0.0)

    # Team 1 has skills data and the best CCWM/AWP too, so it should have the
    # highest pick-list score of the three.
    assert rows[1].pick_list_score > rows[2].pick_list_score > rows[3].pick_list_score

    # Team 2 has no skills data — its score is CCWM+AWP only (weight
    # redistributed), not penalized to zero for the missing component.
    expected_team_2 = (
        db.PICK_LIST_WEIGHTS["ccwm"] + db.PICK_LIST_WEIGHTS["skills"]
    ) * rows[2].percentile_ccwm + db.PICK_LIST_WEIGHTS["awp"] * 100.0  # tied best AWP
    assert rows[2].pick_list_score == pytest.approx(expected_team_2)


def test_archive_completed_seasons_moves_stale_seasons_to_history(engine):
    old_season, current_season = 190, 197

    db.record_event_results(
        engine,
        _event(event_id=1, season_id=old_season),
        [TeamStats(team_id=1, team_num="100A", total_matches=1, qual_matches=1, opr=10.0, dpr=5.0, ccwm=5.0)],
    )
    db.refresh_team_season_summary(engine, old_season)

    db.record_event_results(
        engine,
        _event(event_id=2, season_id=current_season),
        [TeamStats(team_id=1, team_num="100A", total_matches=1, qual_matches=1, opr=12.0, dpr=4.0, ccwm=8.0)],
    )
    db.refresh_team_season_summary(engine, current_season)

    archived = db.archive_completed_seasons(engine)
    assert archived == 1

    from sqlalchemy.orm import Session

    with Session(engine) as session:
        remaining = session.execute(select(db.TeamSeasonSummaryRecord)).scalars().all()
        history = session.execute(select(db.TeamSeasonHistoryRecord)).scalars().all()

    assert {r.season_id for r in remaining} == {current_season}
    assert {r.season_id for r in history} == {old_season}
    assert history[0].team_num == "100A"
    assert history[0].opr_avg == pytest.approx(10.0)
    assert history[0].archived_at is not None

    # Idempotent: calling again with nothing new to archive is a no-op.
    assert db.archive_completed_seasons(engine) == 0


def test_archive_completed_seasons_is_noop_with_only_one_season(engine):
    db.record_event_results(
        engine,
        _event(event_id=1, season_id=190),
        [TeamStats(team_id=1, team_num="100A", total_matches=1, qual_matches=1, opr=1.0, dpr=1.0, ccwm=0.0)],
    )
    db.refresh_team_season_summary(engine, 190)

    assert db.archive_completed_seasons(engine) == 0
    assert db.get_latest_season_id(engine) == 190


def test_in_progress_event_tracking(engine):
    now = datetime(2026, 1, 10, 12, 0, 0, tzinfo=UTC)
    ongoing = _event(
        event_id=1,
        start=datetime(2026, 1, 10, 9, 0, 0, tzinfo=UTC),
        end=datetime(2026, 1, 10, 20, 0, 0, tzinfo=UTC),
    )
    finished = _event(
        event_id=2,
        start=datetime(2026, 1, 8, 9, 0, 0, tzinfo=UTC),
        end=datetime(2026, 1, 8, 20, 0, 0, tzinfo=UTC),
    )

    db.record_event_results(engine, ongoing, [])
    db.record_event_results(engine, finished, [])

    assert db.get_in_progress_event_ids(engine, now) == {ongoing.id}
    assert _as_utc(db.get_oldest_in_progress_event_start(engine, now)) == ongoing.start
