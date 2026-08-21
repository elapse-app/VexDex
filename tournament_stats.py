from __future__ import annotations

import asyncio
import logging

import numpy as np
import trueskill as ts

from fetch_vex import fetch_data
from match import Match
from team_stats import TeamStats

env = ts.TrueSkill()
logger = logging.getLogger(__name__)

ratings: dict[int, ts.Rating] = {}
stats_by_team: dict[int, TeamStats] = {}
stats: list[TeamStats] = []


def reset_state() -> None:
    ratings.clear()
    stats_by_team.clear()
    stats.clear()


async def process_event(event_id, div_ids):
    teams_data = [
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
    res = await asyncio.gather(*(teams_data + matches_data))

    teams = [team for teams in res[: len(div_ids)] for team in teams]
    matches = [match for matches in res[len(div_ids) :] for match in matches]

    await process_matches(teams, matches)


async def process_matches(teams, matches):
    quals: list[Match] = []
    for data in matches:
        match = Match.from_json(data)
        calc_ts(match)
        quals.append(match)

    if not quals:
        return

    for team in teams:
        t = team["team"]
        team_id = int(t["id"])
        if team_id not in stats_by_team:
            stat = TeamStats(team_id=team_id, team_num=str(t["name"]))
            stats_by_team[team_id] = stat
            stats.append(stat)

    opr, dpr = calc_ccwm(quals)
    team_match_counts = _count_team_matches(quals)

    for team_id in opr:
        stat = stats_by_team.get(team_id)
        if stat is None:
            continue

        previous = stat.matches_played
        current = team_match_counts.get(team_id, 0)
        if current <= 0:
            continue

        stat.opr = stat.opr * previous + float(opr.get(team_id, 0.0)) * current
        stat.dpr = stat.dpr * previous + float(dpr.get(team_id, 0.0)) * current
        stat.matches_played = previous + current

        if stat.matches_played == 0:
            continue

        stat.opr /= stat.matches_played
        stat.dpr /= stat.matches_played

        stat.ccwm = stat.opr - stat.dpr

    leaderboard = sorted(ratings.items(), key=lambda item: env.expose(item[1]), reverse=True)
    for i, (team_id, rating) in enumerate(leaderboard):
        stat = stats_by_team.get(team_id)
        if stat is None:
            continue
        stat.ts = env.expose(rating)
        stat.ts_rank = i + 1
        stat.ts_mu = rating.mu
        stat.ts_sigma = rating.sigma


def _count_team_matches(matches: list[Match]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for match in matches:
        for team_id in match.red_teams + match.blue_teams:
            counts[team_id] = counts.get(team_id, 0) + 1
    return counts


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


async def main():
    await process_event(59926, [1])

    leaderboard = sorted(stats, key=lambda item: item.ts, reverse=True)
    for t in leaderboard:
        print(
            f"{t.team_num}: opr={t.opr:.2f}, dpr={t.dpr:.2f}, ccwm={t.ccwm:.2f}, ts={t.ts:.2f}, tsRank={t.ts_rank}, mu={t.ts_mu:.2f}, sigma={t.ts_sigma:.2f}"
        )


if __name__ == "__main__":
    asyncio.run(main())
