import asyncio
import trueskill as ts
from match import MatchType, Match
from numpy import linalg as np
from team_stats import TeamStats
from fetch_re import fetch_data

env = ts.TrueSkill()
ratings = {}
stats = []


async def ingest_matches(event_id, div_id):
    teams = await fetch_data(
        f"https://www.robotevents.com/api/v2/events/{event_id}/divisions/{div_id}/rankings",
        params={"per_page": 250})
    matches = await fetch_data(
        f"https://www.robotevents.com/api/v2/events/{event_id}/divisions/{div_id}/matches",
        params={"per_page": 250})

    await process_matches(teams, matches)


async def process_matches(teams, matches):
    quals = []
    for data in matches:
        match = Match(data)
        if match.match_type != MatchType.QUAL:
            continue
        calc_ts(match)
        quals.append(match)

    for team in teams:
        t = team['team']
        stats.append(TeamStats(t['id'], t['name']))

    opr, dpr = calc_ccwm(quals)
    for team_id in opr.keys():
        stat = next((s for s in stats if s.team_id.id == team_id), -1)
        if stat == -1:
            continue

        stat.opr = opr.get(team_id)
        stat.dpr = dpr.get(team_id)
        stat.ccwm = stat.opr - stat.dpr

    leaderboard = sorted(ratings.items(), key=lambda item: env.expose(item[1]),
                         reverse=True)
    for i, (team_id, rating) in enumerate(leaderboard):
        stat = next((s for s in stats if s.team_id.id == team_id), -1)
        if stat == -1:
            continue
        stat.ts = env.expose(rating)
        stat.ts_rank = i + 1
        stat.ts_mu = rating.mu
        stat.ts_sigma = rating.sigma


def calc_ts(match):
    red_teams = [ratings.get(match.red_teams[0], ts.Rating()),
                 ratings.get(match.red_teams[1], ts.Rating())]
    blue_teams = [ratings.get(match.blue_teams[0], ts.Rating()),
                  ratings.get(match.blue_teams[1], ts.Rating())]
    ranks = [0, 0]
    if match.red_score > match.blue_score:
        ranks = [0, 1]
    elif match.blue_score > match.red_score:
        ranks = [1, 0]
    (red_0, red_1), (blue_0, blue_1) = env.rate([red_teams, blue_teams],
                                                ranks=ranks)

    ratings.update({match.red_teams[0]: red_0})
    ratings.update({match.red_teams[1]: red_1})
    ratings.update({match.blue_teams[0]: blue_0})
    ratings.update({match.blue_teams[1]: blue_1})


def calc_ccwm(matches: list[Match]):
    teams = set(())

    for m in matches:
        teams.update(m.red_teams)
        teams.update(m.blue_teams)

    red_scores = []
    blue_scores = []

    red_match_teams = [{team: 0 for team in teams} for _ in matches]
    blue_match_teams = [{team: 0 for team in teams} for _ in matches]

    for i in range(len(matches)):
        red_scores.append(matches[i].red_score)
        blue_scores.append(matches[i].blue_score)

        red_match_teams[i].update(
            {matches[i].red_teams[0]: 1, matches[i].red_teams[1]: 1})
        blue_match_teams[i].update(
            {matches[i].blue_teams[0]: 1, matches[i].blue_teams[1]: 1})

    match_teams = ([list(match.values()) for match in red_match_teams] +
                   [list(match.values()) for match in blue_match_teams])

    m_scores = red_scores + blue_scores
    m_opp_scores = blue_scores + red_scores
    m_matches = match_teams
    m_matches_t = np.matrix_transpose(match_teams)

    m_opr = np.solve(np.matmul(m_matches_t, m_matches),
                     np.matmul(m_matches_t, m_scores))
    m_dpr = np.solve(np.matmul(m_matches_t, m_matches),
                     np.matmul(m_matches_t, m_opp_scores))

    opr = {t: m_opr[i] for i, t in enumerate(teams)}
    dpr = {t: m_dpr[i] for i, t in enumerate(teams)}

    return opr, dpr


async def main():
    await ingest_matches(59926, 1)

    leaderboard = sorted(stats, key=lambda item: item.ts, reverse=True)
    for t in leaderboard:
        print(
            f"{t.team_id.number}: opr={t.opr:.2f}, dpr={t.dpr:.2f}, ccwm={t.ccwm:.2f}, ts={t.ts:.2f}, tsRank={t.ts_rank}, mu={t.ts_mu:.2f}, sigma={t.ts_sigma:.2f}")


if __name__ == '__main__':
    asyncio.run(main())
