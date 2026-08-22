from __future__ import annotations

import asyncio
import logging

import numpy as np
import trueskill as ts

from award import Award
from fetch_vex import fetch_data
from match import Match, MatchType
from skill import SkillRun
from team_stats import TeamStats

env = ts.TrueSkill()
logger = logging.getLogger(__name__)

# TrueSkill is a continuously evolving belief per team, intentionally kept
# across every event processed in one pipeline run (not reset per event).
ratings: dict[int, ts.Rating] = {}


def reset_state() -> None:
    ratings.clear()


async def fetch_event_data(event_id, div_ids) -> tuple[list, list, list, list]:
    """Fetch raw rankings, matches, skills, and awards JSON for an event. Safe
    to run concurrently across many events — pure I/O, no TrueSkill state
    touched here. Awards are event-wide (not per-division)."""
    rankings_data = [
        fetch_data(
            f"https://events.vex.com/api/v2/events/{event_id}/divisions/{div_id}/rankings",
            params={"per_page": 250},
        )
        for div_id in div_ids
    ]
    matches_data = [
        fetch_data(
            f"https://events.vex.com/api/v2/events/{event_id}/divisions/{div_id}/matches",
            params={"per_page": 250},
        )
        for div_id in div_ids
    ]
    skills_task = fetch_data(
        f"https://events.vex.com/api/v2/events/{event_id}/skills", params={"per_page": 250}
    )
    awards_task = fetch_data(
        f"https://events.vex.com/api/v2/events/{event_id}/awards", params={"per_page": 250}
    )

    res = await asyncio.gather(*(rankings_data + matches_data + [skills_task, awards_task]))

    n = len(div_ids)
    rankings = [row for page in res[:n] for row in page]
    matches = [row for page in res[n : 2 * n] for row in page]
    skills = res[2 * n]
    awards = res[2 * n + 1]
    return rankings, matches, skills, awards


async def process_event(event_id, div_ids) -> list[TeamStats]:
    """Fetch and process a single event. For processing many events together,
    fetch_event_data + process_matches must be run separately so events can be
    scored in chronological order — see update_stats.py."""
    rankings, matches, skills, awards = await fetch_event_data(event_id, div_ids)
    return process_matches(rankings, matches, skills, awards)


def process_matches(rankings, matches, skills=(), awards=()) -> list[TeamStats]:
    """Compute this event's full result set for every team that played:
    win/loss record (overall, qual, elim), ranking-tiebreaker points,
    OPR/DPR/CCWM, the post-event TrueSkill snapshot, skills scores, and
    awards won. Returns one TeamStats per team — a standalone per-event
    result, not blended with any other event.

    Call this in chronological event order when processing multiple events:
    it mutates the module-global TrueSkill `ratings` state, so out-of-order
    calls produce a rating history that doesn't match real match order."""
    parsed_matches = [m for m in (Match.from_json(data) for data in matches) if m.played]
    for match in parsed_matches:
        calc_ts(match)

    if not parsed_matches:
        return []

    team_nums = {int(row["team"]["id"]): str(row["team"]["name"]) for row in rankings}

    opr, dpr = calc_ccwm(parsed_matches)
    results: dict[int, TeamStats] = {}

    # Seed from every team that appears in either matches or rankings — a
    # team can have match results without a final ranking (e.g. withdrew).
    all_team_ids = set(team_nums)
    for match in parsed_matches:
        all_team_ids.update(match.red_teams)
        all_team_ids.update(match.blue_teams)
    for team_id in all_team_ids:
        results[team_id] = TeamStats(team_id=team_id, team_num=team_nums.get(team_id, str(team_id)))

    # Qualification win/loss/draw and matches-played come straight from the
    # rankings payload — it's the authoritative record. Replaying qual match
    # scores ourselves is NOT equivalent: a disqualification or other referee
    # ruling can flip the official result without changing the raw score
    # (confirmed against live data — a team's score-implied qual record was
    # 3-3, but the authoritative rankings record for them was 1-5).
    for row in rankings:
        team_id = int(row["team"]["id"])
        stat = results.get(team_id)
        if stat is None:
            continue
        stat.qual_wins = int(row.get("wins", 0))
        stat.qual_losses = int(row.get("losses", 0))
        stat.qual_draws = int(row.get("ties", 0))
        stat.qual_matches = stat.qual_wins + stat.qual_losses + stat.qual_draws
        stat.wp = int(row.get("wp", 0))
        stat.ap = int(row.get("ap", 0))
        stat.sp = int(row.get("sp", 0))
        stat.average_match_score = float(row.get("average_points", 0.0))
        stat.high_score = int(row.get("high_score", 0))

    # Eliminations have no equivalent authoritative summary endpoint, so this
    # is the only available source — the same DQ/ruling caveat above applies,
    # just with no way to detect or correct it here.
    _tally_elim_records(results, parsed_matches)

    for stat in results.values():
        stat.total_matches = stat.qual_matches + stat.elim_matches
        stat.total_wins = stat.qual_wins + stat.elim_wins
        stat.total_losses = stat.qual_losses + stat.elim_losses
        stat.total_draws = stat.qual_draws + stat.elim_draws

    for team_id, stat in results.items():
        stat.opr = float(opr.get(team_id, 0.0))
        stat.dpr = float(dpr.get(team_id, 0.0))
        stat.ccwm = stat.opr - stat.dpr

    _compute_schedule_metrics(results, opr, parsed_matches)

    for skill_payload in skills:
        run = SkillRun.from_json(skill_payload)
        stat = results.get(run.team_id)
        if stat is None:
            continue
        if run.skill_type == "driver":
            stat.skills_driver = run.score
        elif run.skill_type == "programming":
            stat.skills_prog = run.score

    for award_payload in awards:
        award = Award.from_json(award_payload)
        for team_id in award.team_ids:
            stat = results.get(team_id)
            if stat is None:
                continue
            stat.awards.append((award.title, award.qualifications))

    leaderboard = sorted(ratings.items(), key=lambda item: env.expose(item[1]), reverse=True)
    for i, (team_id, rating) in enumerate(leaderboard):
        stat = results.get(team_id)
        if stat is None:
            continue
        stat.ts = env.expose(rating)
        stat.ts_rank = i + 1
        stat.ts_mu = rating.mu
        stat.ts_sigma = rating.sigma

    return list(results.values())


def _tally_elim_records(results: dict[int, TeamStats], matches: list[Match]) -> None:
    """Fill in elim win-loss-draw records by replaying each elimination
    match's alliance scores — there's no rankings-style authoritative summary
    for eliminations, so this is a best-effort inference from the score."""
    for match in matches:
        if match.match_type != MatchType.ELIM:
            continue

        for team_id, my_score, opp_score in (
            (match.red_teams[0], match.red_score, match.blue_score),
            (match.red_teams[1], match.red_score, match.blue_score),
            (match.blue_teams[0], match.blue_score, match.red_score),
            (match.blue_teams[1], match.blue_score, match.red_score),
        ):
            stat = results.get(team_id)
            if stat is None:
                continue

            stat.elim_matches += 1
            if my_score > opp_score:
                stat.elim_wins += 1
            elif my_score < opp_score:
                stat.elim_losses += 1
            else:
                stat.elim_draws += 1


def _compute_schedule_metrics(
    results: dict[int, TeamStats], opr: dict[int, float], matches: list[Match]
) -> None:
    """Strength of schedule (average opponent OPR, weighted by how often each
    opponent was faced) and field-strength z-score (how this team's OPR
    compares to the rest of the field at this event), both using this event's
    own OPR values — so they mean the same thing across every event."""
    if len(opr) > 1:
        field_oprs = list(opr.values())
        mean_opr = sum(field_oprs) / len(field_oprs)
        variance = sum((v - mean_opr) ** 2 for v in field_oprs) / len(field_oprs)
        stdev_opr = variance**0.5
    else:
        mean_opr = next(iter(opr.values()), 0.0)
        stdev_opr = 0.0

    opponent_oprs: dict[int, list[float]] = {}
    for match in matches:
        for team_id, opponents in (
            (match.red_teams[0], match.blue_teams),
            (match.red_teams[1], match.blue_teams),
            (match.blue_teams[0], match.red_teams),
            (match.blue_teams[1], match.red_teams),
        ):
            opponent_oprs.setdefault(team_id, []).extend(opr.get(o, 0.0) for o in opponents)

    for team_id, stat in results.items():
        faced = opponent_oprs.get(team_id)
        stat.sos = sum(faced) / len(faced) if faced else 0.0
        stat.field_strength_z = (stat.opr - mean_opr) / stdev_opr if stdev_opr else 0.0


def calc_ts(match):
    red_teams = [
        ratings.get(match.red_teams[0], ts.Rating()),
        ratings.get(match.red_teams[1], ts.Rating()),
    ]
    blue_teams = [
        ratings.get(match.blue_teams[0], ts.Rating()),
        ratings.get(match.blue_teams[1], ts.Rating()),
    ]
    ranks = [0, 0]
    if match.red_score > match.blue_score:
        ranks = [0, 1]
    elif match.blue_score > match.red_score:
        ranks = [1, 0]
    (red_0, red_1), (blue_0, blue_1) = env.rate([red_teams, blue_teams], ranks=ranks)

    ratings.update({match.red_teams[0]: red_0})
    ratings.update({match.red_teams[1]: red_1})
    ratings.update({match.blue_teams[0]: blue_0})
    ratings.update({match.blue_teams[1]: blue_1})


def calc_ccwm(matches: list[Match]):
    team_ids: set[int] = set()

    for m in matches:
        team_ids.update(m.red_teams)
        team_ids.update(m.blue_teams)

    teams = sorted(team_ids)

    red_scores = []
    blue_scores = []

    red_match_teams = [dict.fromkeys(teams, 0) for _ in matches]
    blue_match_teams = [dict.fromkeys(teams, 0) for _ in matches]

    for i in range(len(matches)):
        red_scores.append(matches[i].red_score)
        blue_scores.append(matches[i].blue_score)

        red_match_teams[i].update({matches[i].red_teams[0]: 1, matches[i].red_teams[1]: 1})
        blue_match_teams[i].update({matches[i].blue_teams[0]: 1, matches[i].blue_teams[1]: 1})

    match_teams = [list(match.values()) for match in red_match_teams] + [
        list(match.values()) for match in blue_match_teams
    ]

    m_scores = red_scores + blue_scores
    m_opp_scores = blue_scores + red_scores
    m_matches = np.asarray(match_teams, dtype=float)
    m_matches_t = np.matrix_transpose(m_matches)

    lhs = np.matmul(m_matches_t, m_matches)
    rhs_opr = np.matmul(m_matches_t, m_scores)
    rhs_dpr = np.matmul(m_matches_t, m_opp_scores)

    try:
        m_opr = np.linalg.solve(lhs, rhs_opr)
        m_dpr = np.linalg.solve(lhs, rhs_dpr)
    except np.linalg.LinAlgError:
        logger.warning("Singular matrix in OPR/DPR solve, falling back to least squares.")
        m_opr = np.linalg.lstsq(lhs, rhs_opr, rcond=None)[0]
        m_dpr = np.linalg.lstsq(lhs, rhs_dpr, rcond=None)[0]

    opr = {t: m_opr[i] for i, t in enumerate(teams)}
    dpr = {t: m_dpr[i] for i, t in enumerate(teams)}

    return opr, dpr
