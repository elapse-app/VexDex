import asyncio
import importlib
import sys

import pytest


def _reload_tournament_stats(monkeypatch):
    monkeypatch.setenv("VEX_TOKENS", "unit-test-token")

    for module_name in ("tournament_stats", "fetch_vex", "tokens"):
        if module_name in sys.modules:
            del sys.modules[module_name]

    return importlib.import_module("tournament_stats")


def _match_payload(
    match_id: int,
    red_teams: tuple[int, int],
    blue_teams: tuple[int, int],
    red_score: int,
    blue_score: int,
) -> dict:
    return {
        "id": match_id,
        "matchnum": match_id,
        "instance": 1,
        "round": 2,
        "alliances": [
            {
                "teams": [{"team": {"id": red_teams[0]}}, {"team": {"id": red_teams[1]}}],
                "score": red_score,
            },
            {
                "teams": [{"team": {"id": blue_teams[0]}}, {"team": {"id": blue_teams[1]}}],
                "score": blue_score,
            },
        ],
    }


def test_calc_ccwm_handles_singular_matrix(monkeypatch):
    ts_mod = _reload_tournament_stats(monkeypatch)
    match_mod = importlib.import_module("match")

    single_match = match_mod.Match.from_json(
        _match_payload(
            match_id=1,
            red_teams=(1, 2),
            blue_teams=(3, 4),
            red_score=20,
            blue_score=10,
        )
    )

    opr, dpr = ts_mod.calc_ccwm([single_match])

    assert opr[1] == pytest.approx(10.0)
    assert opr[2] == pytest.approx(10.0)
    assert opr[3] == pytest.approx(5.0)
    assert opr[4] == pytest.approx(5.0)

    assert dpr[1] == pytest.approx(5.0)
    assert dpr[2] == pytest.approx(5.0)
    assert dpr[3] == pytest.approx(10.0)
    assert dpr[4] == pytest.approx(10.0)


def test_process_matches_updates_stats_and_trueskill(monkeypatch):
    ts_mod = _reload_tournament_stats(monkeypatch)
    ts_mod.reset_state()

    teams = [
        {"team": {"id": 1, "name": "A"}},
        {"team": {"id": 2, "name": "B"}},
        {"team": {"id": 3, "name": "C"}},
        {"team": {"id": 4, "name": "D"}},
    ]
    matches = [
        _match_payload(
            match_id=1,
            red_teams=(1, 2),
            blue_teams=(3, 4),
            red_score=20,
            blue_score=10,
        )
    ]

    asyncio.run(ts_mod.process_matches(teams, matches))

    assert len(ts_mod.stats) == 4

    team_1 = ts_mod.stats_by_team[1]
    team_3 = ts_mod.stats_by_team[3]

    assert team_1.matches_played == 1
    assert team_3.matches_played == 1

    assert team_1.opr == pytest.approx(10.0)
    assert team_1.dpr == pytest.approx(5.0)
    assert team_1.ccwm == pytest.approx(5.0)

    assert team_3.opr == pytest.approx(5.0)
    assert team_3.dpr == pytest.approx(10.0)
    assert team_3.ccwm == pytest.approx(-5.0)

    assert team_1.ts > team_3.ts
    assert team_1.ts_rank < team_3.ts_rank
