"""Exercises update_stats.update_events end-to-end against a mocked API and a
real (sqlite) database, without any network access. This is the one piece of
the pipeline not already covered by test_db_pipeline.py (persistence) and
test_tournament_stats_logic.py (the OPR/DPR/TrueSkill math): checkpointing,
event ordering, and refresh-run status tracking."""

from __future__ import annotations

import importlib
import sys

import pytest


def _event_payload(event_id: int, sku: str, start: str, end: str, season_id: int) -> dict:
    return {
        "id": event_id,
        "sku": sku,
        "name": f"Event {event_id}",
        "start": start,
        "end": end,
        "season": {"id": season_id},
        "divisions": [{"id": 1}],
    }


def _match_payload(match_id: int, red: tuple, blue: tuple, red_score: int, blue_score: int) -> dict:
    return {
        "id": match_id,
        "matchnum": match_id,
        "instance": 1,
        "round": 2,
        "started": "2026-01-01T00:00:00-05:00",
        "alliances": [
            {"teams": [{"team": {"id": red[0]}}, {"team": {"id": red[1]}}], "score": red_score},
            {"teams": [{"team": {"id": blue[0]}}, {"team": {"id": blue[1]}}], "score": blue_score},
        ],
    }


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.setenv("VEX_TOKENS", "unit-test-token")
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")

    for name in ("update_stats", "tournament_stats", "config", "db", "fetch_vex", "tokens"):
        sys.modules.pop(name, None)

    update_stats = importlib.import_module("update_stats")
    tournament_stats = importlib.import_module("tournament_stats")
    db = importlib.import_module("db")
    return update_stats, tournament_stats, db


def test_update_events_processes_out_of_order_events_chronologically(modules, monkeypatch):
    update_stats, tournament_stats, db = modules

    # API returns the newer event first, to prove the pipeline reorders by
    # event.start rather than trusting API order — TrueSkill correctness
    # depends on processing in real match-chronological order.
    older = _event_payload(1, "RE-V5RC-26-0001", "2026-01-01T00:00:00-05:00",
                            "2026-01-01T12:00:00-05:00", 190)
    newer = _event_payload(2, "RE-V5RC-26-0002", "2026-01-08T00:00:00-05:00",
                            "2026-01-08T12:00:00-05:00", 190)

    older_matches = [_match_payload(1, (1, 2), (3, 4), 30, 10)]
    newer_matches = [_match_payload(2, (1, 2), (3, 4), 10, 30)]
    teams = [
        {"team": {"id": 1, "name": "100A"}},
        {"team": {"id": 2, "name": "100B"}},
        {"team": {"id": 3, "name": "200A"}},
        {"team": {"id": 4, "name": "200B"}},
    ]

    async def fake_fetch_data(url, params=None, **kwargs):
        if "/seasons" in url:
            return [{"id": 190, "program": {"id": 1}, "start": "2026-01-01T00:00:00-05:00",
                      "end": "2026-06-01T00:00:00-05:00"}]
        if url.endswith("/events/"):
            return [newer, older]  # deliberately out of chronological order
        if "/teams/" in url:
            team_id = int(url.rsplit("/", 1)[-1])
            return {"id": team_id, "number": f"{team_id}A", "team_name": None,
                    "grade": "High School", "location": {"region": "CA"}}
        raise AssertionError(f"unexpected fetch_data call: {url}")

    async def fake_fetch_event_data(event_id, div_ids):
        if event_id == 1:
            return teams, older_matches, [], []
        if event_id == 2:
            return teams, newer_matches, [], []
        raise AssertionError(f"unexpected event_id {event_id}")

    monkeypatch.setattr(update_stats, "fetch_data", fake_fetch_data)
    monkeypatch.setattr(update_stats, "fetch_event_data", fake_fetch_event_data)

    events_processed = __import__("asyncio").run(update_stats.update_events(season_id=190))
    assert events_processed == 2

    # Both events landed, in the order the mocked API served them (out of order).
    assert db.get_processed_event_ids(update_stats.engine) == {1, 2}

    # Reference: what team 1's TrueSkill mu should be if processed in the
    # correct chronological order (older event's blowout win, then a loss).
    tournament_stats.reset_state()
    tournament_stats.process_matches(teams, older_matches)
    expected_team_1 = tournament_stats.process_matches(teams, newer_matches)
    expected_mu = next(r.ts_mu for r in expected_team_1 if r.team_id == 1)

    n = db.refresh_team_season_summary(update_stats.engine, 190)
    assert n == 4

    from sqlalchemy.orm import Session

    with Session(update_stats.engine) as session:
        row = session.get(db.TeamSeasonSummaryRecord, {"season_id": 190, "team_id": 1})
    assert row.ts_mu == pytest.approx(expected_mu)
    assert row.events_count == 2

    # A refresh run was recorded and marked successful.
    from sqlalchemy import select

    with Session(update_stats.engine) as session:
        run = session.execute(
            select(db.DatasetRefreshRunRecord).order_by(db.DatasetRefreshRunRecord.run_id.desc())
        ).scalars().first()
    assert run.status == "succeeded"
    assert run.events_processed == 2
    assert run.teams_upserted == 4


def test_update_events_skips_already_processed_events(modules, monkeypatch):
    update_stats, tournament_stats, db = modules

    event = _event_payload(1, "RE-V5RC-26-0001", "2020-01-01T00:00:00-05:00",
                            "2020-01-01T12:00:00-05:00", 190)
    matches = [_match_payload(1, (1, 2), (3, 4), 30, 10)]
    teams = [
        {"team": {"id": 1, "name": "100A"}},
        {"team": {"id": 2, "name": "100B"}},
        {"team": {"id": 3, "name": "200A"}},
        {"team": {"id": 4, "name": "200B"}},
    ]

    async def fake_fetch_data(url, params=None, **kwargs):
        if "/seasons" in url:
            return [{"id": 190, "program": {"id": 1}, "start": "2020-01-01T00:00:00-05:00",
                      "end": "2020-06-01T00:00:00-05:00"}]
        if url.endswith("/events/"):
            return [event]
        if "/teams/" in url:
            team_id = int(url.rsplit("/", 1)[-1])
            return {"id": team_id, "number": f"{team_id}A", "team_name": None,
                    "grade": "High School", "location": {"region": "CA"}}
        raise AssertionError(f"unexpected fetch_data call: {url}")

    async def fake_fetch_event_data(event_id, div_ids):
        return teams, matches, [], []

    monkeypatch.setattr(update_stats, "fetch_data", fake_fetch_data)
    monkeypatch.setattr(update_stats, "fetch_event_data", fake_fetch_event_data)

    import asyncio

    first_run = asyncio.run(update_stats.update_events(season_id=190))
    assert first_run == 1

    # Same event served again, well in the past (not "in progress") — the
    # checkpoint should skip it entirely on the second run.
    second_run = asyncio.run(update_stats.update_events(season_id=190))
    assert second_run == 0
