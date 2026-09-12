"""Endpoint-level tests for the new Phase 3 surface (award history, pick-list)
against a real sqlite DB through the actual FastAPI app — not just the db.py
functions in isolation."""

import importlib
import os
import sys
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")

    for name in ("api", "db"):
        sys.modules.pop(name, None)

    api = importlib.import_module("api")
    db = importlib.import_module("db")
    from fastapi.testclient import TestClient

    from event import Event
    from team_stats import TeamStats

    test_db_url = os.getenv("TEST_DATABASE_URL")
    if test_db_url:
        # Real Postgres — no cross-thread sqlite quirk to work around, and
        # worth exercising since the JSON column (team_awards) is new.
        test_engine = create_engine(test_db_url, future=True)
    else:
        # TestClient runs each request in a worker thread, and plain sqlite
        # ":memory:" gives each new connection its own private database — the
        # request thread wouldn't see any data the test thread just wrote. A
        # StaticPool keeps every connection on one shared in-memory database.
        test_engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    db.ensure_schema(test_engine)
    api.engine = test_engine

    # Every data route now requires a bearer token; mint one and make it the
    # default header so the existing endpoint tests exercise the happy path.
    raw_token = db.create_api_token(test_engine, "test")
    authed = TestClient(api.app, headers={"Authorization": f"Bearer {raw_token}"})

    try:
        yield authed, api, db, Event, TeamStats
    finally:
        db.Base.metadata.drop_all(test_engine)


def _event(event_id, season_id=190, start=None):
    from event import Event

    start = start or datetime(2026, 1, 10, tzinfo=UTC)
    return Event(
        id=event_id,
        sku=f"RE-V5RC-26-{event_id:04d}",
        name=f"Test Event {event_id}",
        start=start,
        end=start,
        season_id=season_id,
        divisions_id=[1],
    )


def test_award_history_endpoint_returns_chronological_awards(client):
    tc, api, db, Event, TeamStats = client

    team = TeamStats(team_id=1, team_num="100A", total_matches=1, qual_matches=1)
    team.awards = [("Excellence Award", ["World Championship"])]
    db.record_event_results(api.engine, _event(1, start=datetime(2026, 1, 1, tzinfo=UTC)), [team])

    team2 = TeamStats(team_id=1, team_num="100A", total_matches=1, qual_matches=1)
    team2.awards = [("Design Award", ["Event Region Championship"])]
    db.record_event_results(api.engine, _event(2, start=datetime(2026, 1, 8, tzinfo=UTC)), [team2])

    resp = tc.get("/api/v1/seasons/190/teams/1/awards")
    assert resp.status_code == 200
    body = resp.json()
    assert body["team_num"] == "100A"
    assert len(body["awards"]) == 2
    # Chronological: event 1 (Jan 1) before event 2 (Jan 8).
    assert body["awards"][0]["title"] == "Excellence Award"
    assert body["awards"][0]["qualifications"] == ["World Championship"]
    assert body["awards"][1]["title"] == "Design Award"


def test_award_history_empty_for_team_with_no_awards(client):
    tc, api, db, Event, TeamStats = client

    team = TeamStats(team_id=1, team_num="100A", total_matches=1, qual_matches=1)
    db.record_event_results(api.engine, _event(1), [team])

    resp = tc.get("/api/v1/seasons/190/teams/1/awards")
    assert resp.status_code == 200
    assert resp.json()["awards"] == []


def test_pick_list_scopes_to_teams_at_the_event_and_excludes_requested_teams(client):
    tc, api, db, Event, TeamStats = client
    engine = api.engine

    event = _event(1)
    # Team 3 is the best by CCWM but attends a DIFFERENT event — must not
    # appear in event 1's pick list even though it's in the same season.
    other_event = _event(2)

    db.record_event_results(
        engine,
        event,
        [
            TeamStats(team_id=1, team_num="1A", total_matches=1, qual_matches=1, opr=10.0, ccwm=10.0),
            TeamStats(team_id=2, team_num="2A", total_matches=1, qual_matches=1, opr=20.0, ccwm=20.0),
        ],
    )
    db.record_event_results(
        engine,
        other_event,
        [TeamStats(team_id=3, team_num="3A", total_matches=1, qual_matches=1, opr=99.0, ccwm=99.0)],
    )
    db.refresh_team_season_summary(engine, 190)

    resp = tc.get("/api/v1/events/1/pick-list")
    assert resp.status_code == 200
    body = resp.json()
    team_ids = [item["team_id"] for item in body["items"]]
    assert team_ids == [2, 1]  # team 2 has higher CCWM -> higher pick_list_score
    assert 3 not in team_ids  # not at this event, excluded from the candidate pool

    resp2 = tc.get("/api/v1/events/1/pick-list", params={"exclude": [2]})
    assert [item["team_id"] for item in resp2.json()["items"]] == [1]


def test_pick_list_unknown_event_is_404(client):
    tc, api, db, Event, TeamStats = client
    resp = tc.get("/api/v1/events/999/pick-list")
    assert resp.status_code == 404


def test_trend_endpoint_orders_chronologically(client):
    tc, api, db, Event, TeamStats = client
    engine = api.engine

    db.record_event_results(
        engine,
        _event(1, start=datetime(2026, 1, 1, tzinfo=UTC)),
        [TeamStats(team_id=1, team_num="1A", total_matches=1, qual_matches=1, opr=10.0)],
    )
    db.record_event_results(
        engine,
        _event(2, start=datetime(2026, 1, 8, tzinfo=UTC)),
        [TeamStats(team_id=1, team_num="1A", total_matches=1, qual_matches=1, opr=20.0)],
    )

    resp = tc.get("/api/v1/seasons/190/teams/1/trend")
    assert resp.status_code == 200
    points = resp.json()["points"]
    assert [p["opr"] for p in points] == [10.0, 20.0]


def test_team_response_includes_region_ts_rank(client):
    tc, api, db, Event, TeamStats = client
    engine = api.engine

    team_1 = TeamStats(team_id=1, team_num="1A", total_matches=1, qual_matches=1, ts=20.0)
    team_2 = TeamStats(team_id=2, team_num="2A", total_matches=1, qual_matches=1, ts=15.0)
    db.record_event_results(engine, _event(1), [team_1, team_2])

    from team_profile import TeamProfile

    db.record_team_profiles(
        engine,
        [
            TeamProfile(team_id=1, team_num="1A", team_name="A", grade="High School", region="TX"),
            TeamProfile(team_id=2, team_num="2A", team_name="B", grade="High School", region="TX"),
        ],
    )
    db.refresh_team_season_summary(engine, 190)

    resp = tc.get("/api/v1/seasons/190/teams/1")
    assert resp.status_code == 200
    body = resp.json()
    assert "region_ts_rank" in body
    assert body["region_ts_rank"] == 1  # team 1 has higher ts_exposed within TX

    resp2 = tc.get("/api/v1/seasons/190/teams/2")
    assert resp2.json()["region_ts_rank"] == 2


def test_teams_search_matches_partial_team_number(client):
    tc, api, db, Event, TeamStats = client
    engine = api.engine

    db.record_event_results(
        engine,
        _event(1),
        [
            TeamStats(team_id=1, team_num="90241A", total_matches=1, qual_matches=1),
            TeamStats(team_id=2, team_num="12141A", total_matches=1, qual_matches=1),
        ],
    )
    db.refresh_team_season_summary(engine, 190)

    resp = tc.get("/api/v1/seasons/190/teams", params={"search": "0241"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert [item["team_num"] for item in body["items"]] == ["90241A"]


def test_teams_search_matches_partial_team_name_case_insensitively(client):
    tc, api, db, Event, TeamStats = client
    engine = api.engine

    from team_profile import TeamProfile

    db.record_event_results(
        engine,
        _event(1),
        [
            TeamStats(team_id=1, team_num="1A", total_matches=1, qual_matches=1),
            TeamStats(team_id=2, team_num="2A", total_matches=1, qual_matches=1),
        ],
    )
    db.record_team_profiles(
        engine,
        [
            TeamProfile(team_id=1, team_num="1A", team_name="Rushdown Robotics", grade="High School", region="ON"),
            TeamProfile(team_id=2, team_num="2A", team_name="Checkmate", grade="High School", region="ON"),
        ],
    )
    db.refresh_team_season_summary(engine, 190)

    resp = tc.get("/api/v1/seasons/190/teams", params={"search": "rushDOWN"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["team_name"] == "Rushdown Robotics"


def test_archived_season_still_readable_through_the_same_routes(client):
    tc, api, db, Event, TeamStats = client
    engine = api.engine
    old_season, current_season = 190, 197

    db.record_event_results(
        engine,
        _event(1, season_id=old_season),
        [TeamStats(team_id=1, team_num="1A", total_matches=1, qual_matches=1, opr=10.0, ccwm=10.0)],
    )
    db.refresh_team_season_summary(engine, old_season)

    db.record_event_results(
        engine,
        _event(2, season_id=current_season),
        [TeamStats(team_id=1, team_num="1A", total_matches=1, qual_matches=1, opr=20.0, ccwm=20.0)],
    )
    db.refresh_team_season_summary(engine, current_season)

    archived = db.archive_completed_seasons(engine)
    assert archived == 1

    # The season picker still lists both seasons, current one first.
    seasons_resp = tc.get("/api/v1/seasons")
    assert seasons_resp.status_code == 200
    season_ids = [s["season_id"] for s in seasons_resp.json()]
    assert season_ids == [current_season, old_season]

    # The archived season's leaderboard still resolves, from history now.
    archived_resp = tc.get(f"/api/v1/seasons/{old_season}/teams")
    assert archived_resp.status_code == 200
    body = archived_resp.json()
    assert body["total"] == 1
    assert body["items"][0]["ccwm_avg"] == pytest.approx(10.0)

    # The current season's single-team lookup still comes from the live table.
    current_resp = tc.get(f"/api/v1/seasons/{current_season}/teams/1")
    assert current_resp.status_code == 200
    assert current_resp.json()["ccwm_avg"] == pytest.approx(20.0)

    # And the un-prefixed "current" routes still resolve to the live season.
    top_level_resp = tc.get("/api/v1/teams/1")
    assert top_level_resp.status_code == 200
    assert top_level_resp.json()["season_id"] == current_season


def test_teams_search_with_no_matches_returns_empty(client):
    tc, api, db, Event, TeamStats = client
    engine = api.engine

    db.record_event_results(
        engine, _event(1), [TeamStats(team_id=1, team_num="1A", total_matches=1, qual_matches=1)]
    )
    db.refresh_team_season_summary(engine, 190)

    resp = tc.get("/api/v1/seasons/190/teams", params={"search": "zzz_no_such_team"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []


def test_data_endpoint_requires_a_token(client):
    tc, api, db, Event, TeamStats = client
    from fastapi.testclient import TestClient

    bare = TestClient(api.app)
    resp = bare.get("/api/v1/teams")
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == "Bearer"


def test_data_endpoint_rejects_a_bad_token(client):
    tc, api, db, Event, TeamStats = client
    from fastapi.testclient import TestClient

    bad = TestClient(api.app, headers={"Authorization": "Bearer nope"})
    assert bad.get("/api/v1/teams").status_code == 401


def test_data_endpoint_rejects_a_revoked_token(client):
    tc, api, db, Event, TeamStats = client
    from fastapi.testclient import TestClient

    raw = db.create_api_token(api.engine, "temp")
    tmp = TestClient(api.app, headers={"Authorization": f"Bearer {raw}"})
    # A team must exist so a 200 would otherwise be possible.
    db.record_event_results(
        api.engine, _event(1), [TeamStats(team_id=1, team_num="1A", total_matches=1, qual_matches=1)]
    )
    db.refresh_team_season_summary(api.engine, 190)
    assert tmp.get("/api/v1/teams").status_code == 200

    token_id = next(t.token_id for t in db.list_api_tokens(api.engine) if t.label == "temp")
    db.revoke_api_token(api.engine, token_id=token_id)
    assert tmp.get("/api/v1/teams").status_code == 401


def test_health_is_public(client):
    tc, api, db, Event, TeamStats = client
    from fastapi.testclient import TestClient

    bare = TestClient(api.app)
    resp = bare.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_get_responses_are_cached_but_still_require_a_token(client):
    tc, api, db, Event, TeamStats = client
    from fastapi.testclient import TestClient

    db.record_event_results(
        api.engine, _event(1), [TeamStats(team_id=1, team_num="1A", total_matches=1, qual_matches=1)]
    )
    db.refresh_team_season_summary(api.engine, 190)

    first = tc.get("/api/v1/teams")
    assert first.status_code == 200
    assert first.headers["x-cache"] == "MISS"
    assert "max-age" in first.headers["cache-control"]

    second = tc.get("/api/v1/teams")
    assert second.status_code == 200
    assert second.headers["x-cache"] == "HIT"
    assert second.json() == first.json()

    # A warm cache must not become an auth bypass.
    bare = TestClient(api.app)
    assert bare.get("/api/v1/teams").status_code == 401
