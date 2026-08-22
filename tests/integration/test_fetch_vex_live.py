import asyncio
import importlib
import math
import os
import sys
from datetime import UTC, datetime

import pytest


def _require_live_test_env():
    if os.getenv("RUN_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_INTEGRATION_TESTS=1 to enable live HTTP integration tests.")

    if not os.getenv("VEX_TOKENS", "").strip():
        pytest.skip("VEX_TOKENS must be set for live VEX Events integration tests.")


def _reload_fetch_vex_with_env(monkeypatch):
    token_value = os.getenv("VEX_TOKENS", "").strip()
    monkeypatch.setenv("VEX_TOKENS", token_value)

    for module_name in ("fetch_vex", "tokens"):
        if module_name in sys.modules:
            del sys.modules[module_name]

    return importlib.import_module("fetch_vex")


def _reload_tournament_stats_with_env(monkeypatch):
    token_value = os.getenv("VEX_TOKENS", "").strip()
    monkeypatch.setenv("VEX_TOKENS", token_value)

    for module_name in ("tournament_stats", "fetch_vex", "tokens"):
        if module_name in sys.modules:
            del sys.modules[module_name]

    return importlib.import_module("tournament_stats")


def _find_processable_division(fetch_vex, season_id: int):
    events = asyncio.run(
        fetch_vex.fetch_data(
            "https://events.vex.com/api/v2/events/",
            params={
                "season": season_id,
                "end": datetime.now(UTC).isoformat(),
                "per_page": 50,
            },
            max_concurrency=3,
            default_backoff=1,
            max_backoff=8,
        )
    )

    if not isinstance(events, list) or not events:
        pytest.skip("No events returned by VEX Events for integration calculation tests.")

    for event in events:
        divisions = event.get("divisions", [])
        if not divisions:
            continue

        event_id = int(event["id"])
        division_id = int(divisions[0]["id"])

        matches = asyncio.run(
            fetch_vex.fetch_data(
                f"https://events.vex.com/api/v2/events/{event_id}/divisions/{division_id}/matches",
                params={"per_page": 250},
                max_concurrency=3,
                default_backoff=1,
                max_backoff=8,
            )
        )
        teams = asyncio.run(
            fetch_vex.fetch_data(
                f"https://events.vex.com/api/v2/events/{event_id}/divisions/{division_id}/rankings",
                params={"per_page": 250},
                max_concurrency=3,
                default_backoff=1,
                max_backoff=8,
            )
        )

        if isinstance(matches, list) and matches and isinstance(teams, list) and teams:
            return event_id, division_id, teams, matches

    pytest.skip("No processable event/division with matches found for this season.")


@pytest.mark.integration
def test_live_fetch_single_season_details(monkeypatch):
    _require_live_test_env()

    fetch_vex = _reload_fetch_vex_with_env(monkeypatch)

    payload = asyncio.run(
        fetch_vex.fetch_data(
            "https://events.vex.com/api/v2/seasons/190",
            max_concurrency=1,
            default_backoff=1,
            max_backoff=8,
        )
    )

    assert isinstance(payload, dict)
    assert int(payload["id"]) == 190
    assert "name" in payload


@pytest.mark.integration
def test_live_calculations_process_event_produces_metrics(monkeypatch):
    _require_live_test_env()

    fetch_vex = _reload_fetch_vex_with_env(monkeypatch)
    season_id = int(os.getenv("VEX_SEASON_ID", "190"))
    event_id, division_id, _, _ = _find_processable_division(fetch_vex, season_id)

    ts_module = _reload_tournament_stats_with_env(monkeypatch)
    ts_module.reset_state()

    results = asyncio.run(ts_module.process_event(event_id, [division_id]))

    assert results

    teams_with_matches = [team for team in results if team.matches_played > 0]
    assert teams_with_matches

    for team in teams_with_matches:
        assert math.isfinite(team.opr)
        assert math.isfinite(team.dpr)
        assert math.isfinite(team.ccwm)
        assert math.isfinite(team.ts)
        assert math.isfinite(team.ts_mu)
        assert math.isfinite(team.ts_sigma)
        assert team.ccwm == pytest.approx(team.opr - team.dpr, rel=1e-6, abs=1e-6)


@pytest.mark.integration
def test_live_calculations_process_matches_rank_consistency(monkeypatch):
    _require_live_test_env()

    fetch_vex = _reload_fetch_vex_with_env(monkeypatch)
    season_id = int(os.getenv("VEX_SEASON_ID", "190"))
    _, _, teams, matches = _find_processable_division(fetch_vex, season_id)

    ts_module = _reload_tournament_stats_with_env(monkeypatch)
    ts_module.reset_state()

    results = ts_module.process_matches(teams, matches)

    ranked = [team for team in results if team.ts_rank > 0]
    assert ranked

    observed_ranks = sorted(team.ts_rank for team in ranked)
    assert observed_ranks == list(range(1, len(observed_ranks) + 1))
