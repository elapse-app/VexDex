import asyncio
from datetime import datetime
from tournament_stats import process_event, stats
from event import Event
from fetch_re import fetch_data

last_updated = datetime(2025, 12, 17)


async def get_events():
    events_json = await fetch_data(
        f'https://www.robotevents.com/api/v2/events/',
        params={'start': last_updated.isoformat(),
                'end': datetime.now().isoformat(), 'season': 197})
    events = []
    for event in events_json:
        events.append(Event.from_json(event))

    matches = [process_event(event.id, event.divisions_id) for event in events]
    await asyncio.gather(*matches)

    leaderboard = sorted(stats, key=lambda item: item.ts, reverse=True)
    for t in leaderboard:
        print(
            f"{t.team_id.number}: matches={t.matches_played}, opr={t.opr:.2f}, dpr={t.dpr:.2f}, ccwm={t.ccwm:.2f}, ts={t.ts:.2f}, tsRank={t.ts_rank}, mu={t.ts_mu:.2f}, sigma={t.ts_sigma:.2f}")


async def main():
    await get_events()


if __name__ == '__main__':
    asyncio.run(main())
