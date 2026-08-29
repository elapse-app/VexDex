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
    round_code: int = 2,
    played: bool = True,
) -> dict:
    return {
        "id": match_id,
        "matchnum": match_id,
        "instance": 1,
        "round": round_code,
        "started": "2026-01-10T09:00:00-05:00" if played else None,
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


def _ranking_row(
    team_id: int, team_num: str, *, wins=0, losses=0, ties=0, wp=0, ap=0, sp=0, avg=0.0, high=0
) -> dict:
    return {
        "team": {"id": team_id, "name": team_num},
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "wp": wp,
        "ap": ap,
        "sp": sp,
        "average_points": avg,
        "high_score": high,
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

    rankings = [
        _ranking_row(1, "100A", wins=1, losses=0, wp=2, ap=6, sp=10, avg=20.0, high=20),
        _ranking_row(2, "100B", wins=1, losses=0, wp=2, ap=6, sp=10, avg=20.0, high=20),
        _ranking_row(3, "200A", wins=0, losses=1, wp=0, ap=2, sp=5, avg=10.0, high=10),
        _ranking_row(4, "200B", wins=0, losses=1, wp=0, ap=2, sp=5, avg=10.0, high=10),
    ]
    matches = [
        _match_payload(match_id=1, red_teams=(1, 2), blue_teams=(3, 4), red_score=20, blue_score=10),
    ]

    results = ts_mod.process_matches(rankings, matches)
    results_by_team = {r.team_id: r for r in results}

    assert len(results) == 4

    team_1 = results_by_team[1]
    team_3 = results_by_team[3]

    assert team_1.total_matches == 1
    assert team_3.total_matches == 1

    assert team_1.opr == pytest.approx(10.0)
    assert team_1.dpr == pytest.approx(5.0)
    assert team_1.ccwm == pytest.approx(5.0)

    assert team_3.opr == pytest.approx(5.0)
    assert team_3.dpr == pytest.approx(10.0)
    assert team_3.ccwm == pytest.approx(-5.0)

    assert team_1.ts > team_3.ts
    assert team_1.ts_rank < team_3.ts_rank

    # SOS: team 1's only opponents (3, 4) both have OPR 5.0.
    assert team_1.sos == pytest.approx(5.0)
    # Field-strength z: field is [10, 10, 5, 5], mean 7.5, stdev 2.5.
    assert team_1.field_strength_z == pytest.approx(1.0)
    assert team_3.field_strength_z == pytest.approx(-1.0)

    # Win/loss record comes from the rankings payload (authoritative), not
    # replayed from the match score — see test below for why that matters.
    assert team_1.total_wins == 1 and team_1.qual_wins == 1 and team_1.elim_wins == 0
    assert team_3.total_losses == 1 and team_3.qual_losses == 1

    # wp/ap/sp come straight from the rankings row for that team.
    assert team_1.wp == 2 and team_1.ap == 6 and team_1.sp == 10
    assert team_1.avg_ap == pytest.approx(6.0)  # ap / qual_matches
    assert team_1.avg_wp == pytest.approx(2.0)
    # AWP estimate: wp - 2*wins - ties = 2 - 2*1 - 0 = 0 (won without an AWP bonus)
    assert team_1.avg_awp == pytest.approx(0.0)


def test_sos_weights_by_how_often_each_opponent_is_faced(monkeypatch):
    ts_mod = _reload_tournament_stats(monkeypatch)
    ts_mod.reset_state()

    # Team 1 faces team 3 (OPR 5) once and team 5 (OPR 15) twice, so SOS
    # should be (5 + 15 + 15) / 3, not a plain average of distinct opponents.
    rankings = [_ranking_row(t, f"{t}A", wins=1, losses=0) for t in (1, 2, 3, 4, 5, 6)]
    matches = [
        _match_payload(1, (1, 2), (3, 4), red_score=20, blue_score=10),
        _match_payload(2, (1, 2), (5, 6), red_score=20, blue_score=30),
        _match_payload(3, (1, 2), (5, 6), red_score=20, blue_score=30),
    ]

    results = {r.team_id: r for r in ts_mod.process_matches(rankings, matches)}

    opr_3, opr_5 = results[3].opr, results[5].opr
    expected_sos = (opr_3 + 2 * opr_5) / 3
    assert results[1].sos == pytest.approx(expected_sos)


def test_process_matches_trusts_rankings_over_raw_score_for_qual_record(monkeypatch):
    # Confirmed against live data: a disqualification or other ruling can
    # flip the official qual result without changing the raw alliance score.
    # Team 1 "wins" 20-10 by score, but the rankings payload says they lost.
    ts_mod = _reload_tournament_stats(monkeypatch)
    ts_mod.reset_state()

    rankings = [
        _ranking_row(1, "100A", wins=0, losses=1, wp=0),
        _ranking_row(2, "100B", wins=0, losses=1, wp=0),
        _ranking_row(3, "200A", wins=1, losses=0, wp=2),
        _ranking_row(4, "200B", wins=1, losses=0, wp=2),
    ]
    matches = [_match_payload(1, (1, 2), (3, 4), red_score=20, blue_score=10)]

    results = {r.team_id: r for r in ts_mod.process_matches(rankings, matches)}

    assert results[1].qual_wins == 0 and results[1].qual_losses == 1
    assert results[3].qual_wins == 1 and results[3].qual_losses == 0
    # avg_awp never goes negative precisely because we trust this source.
    assert results[1].avg_awp >= 0


def test_process_matches_splits_qual_and_elim_records(monkeypatch):
    ts_mod = _reload_tournament_stats(monkeypatch)
    ts_mod.reset_state()

    rankings = [_ranking_row(t, f"{t}A", wins=1, losses=0) for t in (1, 2)] + [
        _ranking_row(t, f"{t}A", wins=0, losses=1) for t in (3, 4)
    ]
    matches = [
        _match_payload(1, (1, 2), (3, 4), red_score=20, blue_score=10, round_code=2),  # qual win
        _match_payload(2, (1, 2), (3, 4), red_score=5, blue_score=15, round_code=3),  # elim loss
    ]

    results = {r.team_id: r for r in ts_mod.process_matches(rankings, matches)}
    team_1 = results[1]

    assert team_1.total_matches == 2
    assert team_1.qual_matches == 1 and team_1.qual_wins == 1
    assert team_1.elim_matches == 1 and team_1.elim_losses == 1
    assert team_1.total_wins == 1 and team_1.total_losses == 1


def test_process_matches_ignores_unplayed_placeholder_matches(monkeypatch):
    # Real data caught this: a scheduled-but-never-played match shows up with
    # score 0-0 and started=null. It must not feed OPR/DPR or TrueSkill —
    # treating it as a real 0-0 draw corrupts every stat.
    ts_mod = _reload_tournament_stats(monkeypatch)
    ts_mod.reset_state()

    rankings = [_ranking_row(t, f"{t}A", wins=1, losses=0, wp=2, ap=6) for t in (1, 2)] + [
        _ranking_row(t, f"{t}A", wins=0, losses=1) for t in (3, 4)
    ]
    matches = [
        _match_payload(1, (1, 2), (3, 4), red_score=20, blue_score=10, played=True),
        _match_payload(2, (1, 2), (3, 4), red_score=0, blue_score=0, played=False),
    ]

    results = {r.team_id: r for r in ts_mod.process_matches(rankings, matches)}

    assert results[1].opr == pytest.approx(10.0)  # only the played match feeds OPR
    assert results[1].total_wins == 1


def test_process_matches_skips_malformed_match_instead_of_raising(monkeypatch):
    # Real data caught this too: an unpaired elimination bracket slot can
    # come back with an empty alliance `teams` list. process_matches must
    # skip it rather than crash the whole event's processing on it.
    ts_mod = _reload_tournament_stats(monkeypatch)
    ts_mod.reset_state()

    rankings = [_ranking_row(t, f"{t}A", wins=1, losses=0, wp=2, ap=6) for t in (1, 2)] + [
        _ranking_row(t, f"{t}A", wins=0, losses=1) for t in (3, 4)
    ]
    malformed = _match_payload(2, (1, 2), (3, 4), red_score=0, blue_score=0)
    malformed["alliances"][0]["teams"] = []
    matches = [
        _match_payload(1, (1, 2), (3, 4), red_score=20, blue_score=10, played=True),
        malformed,
    ]

    results = {r.team_id: r for r in ts_mod.process_matches(rankings, matches)}

    assert results[1].opr == pytest.approx(10.0)  # only the well-formed match feeds OPR
    assert results[1].total_wins == 1


def test_process_matches_attaches_skills_and_awards(monkeypatch):
    ts_mod = _reload_tournament_stats(monkeypatch)
    ts_mod.reset_state()

    rankings = [_ranking_row(t, f"{t}A", wins=1, losses=0) for t in (1, 2, 3, 4)]
    matches = [_match_payload(1, (1, 2), (3, 4), red_score=20, blue_score=10)]
    skills = [
        {"team": {"id": 1, "name": "1A"}, "type": "driver", "score": 40, "attempts": 2, "rank": 1},
        {"team": {"id": 1, "name": "1A"}, "type": "programming", "score": 10, "attempts": 3, "rank": 2},
    ]
    awards = [
        {
            "title": "Excellence Award (V5)",
            "qualifications": ["World Championship"],
            "teamWinners": [{"team": {"id": 1}}],
        },
        {
            "title": "Design Award (V5)",
            "qualifications": ["Event Region Championship"],
            "teamWinners": [{"team": {"id": 3}}],
        },
    ]

    results = {r.team_id: r for r in ts_mod.process_matches(rankings, matches, skills, awards)}

    assert results[1].skills_driver == 40
    assert results[1].skills_prog == 10
    assert results[1].skills_total == 50
    assert results[1].qualed_worlds is True
    assert results[1].qualed_regionals is False

    assert results[3].qualed_worlds is False
    assert results[3].qualed_regionals is True

    # A team with no skills runs has no skills data at all, not zeros.
    assert results[2].skills_driver is None
    assert results[2].skills_total is None
