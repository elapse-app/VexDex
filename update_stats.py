import argparse
import asyncio
import logging
from datetime import datetime
from typing import Any

from config import load_app_config
from db import (
    complete_refresh_run,
    ensure_schema,
    get_engine,
    get_in_progress_event_ids,
    get_last_updated_event_start,
    get_oldest_in_progress_event_start,
    get_processed_event_ids,
    mark_event_processed,
    start_refresh_run,
    upsert_team_season_stats,
    upsert_team_stats,
)
from event import Event
from fetch_vex import fetch_data
from tournament_stats import process_event, reset_state, stats

engine = get_engine()
ensure_schema(engine)

logger = logging.getLogger(__name__)


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


async def resolve_incremental_season_id(config_season_id: int | None) -> int:
    if config_season_id is not None:
        return config_season_id

    seasons_json = await fetch_data(
        "https://events.vex.com/api/v2/seasons",
        params={"per_page": 250},
    )
    if not isinstance(seasons_json, list) or not seasons_json:
        raise RuntimeError("Unable to determine latest season from VEX Events API.")

    candidates: list[tuple[datetime, int]] = []
    for season in seasons_json:
        if not isinstance(season, dict):
            continue

        program = season.get("program")
        if not isinstance(program, dict):
            continue

        try:
            program_id = int(program.get("id"))
        except (TypeError, ValueError):
            continue

        if program_id != 1:
            continue

        raw_id = season.get("id")
        if raw_id is None:
            continue

        try:
            season_id = int(raw_id)
        except (TypeError, ValueError):
            continue

        season_start = _parse_iso_datetime(season.get("start"))
        season_end = _parse_iso_datetime(season.get("end"))
        season_marker = season_end or season_start or datetime.min
        candidates.append((season_marker, season_id))

    if not candidates:
        raise RuntimeError(
            "VEX Events seasons payload did not include parseable V5RC season IDs."
        )

    _, latest_season_id = max(candidates)
    logger.info("Resolved latest season id as %s from VEX Events.", latest_season_id)
    return latest_season_id


async def update_events(*, season_id: int | None = None, include_entire_season: bool = False) -> int:
    config = load_app_config()
    if season_id is not None:
        target_season_id = season_id
    elif include_entire_season:
        if config.season_id is None:
            raise RuntimeError(
                "Manual season backfill requires --season-backfill <season_id> or VEX_SEASON_ID."
            )
        target_season_id = config.season_id
    else:
        target_season_id = await resolve_incremental_season_id(config.season_id)

    run_id = start_refresh_run(engine, season_id=target_season_id)

    events_processed = 0
    teams_upserted = 0

    try:
        now = datetime.now()
        processed_events = get_processed_event_ids(engine)
        in_progress_event_ids = get_in_progress_event_ids(engine, now)

        params: dict[str, str | int]
        if include_entire_season:
            logger.info(
                "Running full-season manual backfill for season %s.", target_season_id
            )
            params = {
                "season": target_season_id,
                "end": now.isoformat(),
            }
        else:
            last_updated_start = get_last_updated_event_start(engine)
            oldest_in_progress_start = get_oldest_in_progress_event_start(engine, now)

            start = last_updated_start or config.event_start
            if oldest_in_progress_start is not None and oldest_in_progress_start < start:
                start = oldest_in_progress_start

            params = {
                "start": start.isoformat(),
                "end": now.isoformat(),
                "season": target_season_id,
            }

        events_json = await fetch_data(
            "https://events.vex.com/api/v2/events/",
            params=params,
        )

        if not isinstance(events_json, list):
            raise RuntimeError("Expected event list payload from VEX Events API.")

        events = []
        for event in events_json:
            parsed_event = Event.from_json(event)
            if parsed_event.id in processed_events and parsed_event.id not in in_progress_event_ids:
                continue
            events.append(parsed_event)

        if not events:
            logger.info("No new events to process.")
            complete_refresh_run(
                engine,
                run_id=run_id,
                status="succeeded",
                events_processed=0,
                teams_upserted=0,
            )
            return 0

        reset_state()
        matches = [process_event(event.id, event.divisions_id) for event in events]
        await asyncio.gather(*matches)

        for event in events:
            mark_event_processed(engine, event.id, event.start, event.end)

        upsert_team_stats(engine, stats)
        upsert_team_season_stats(engine, target_season_id, stats)

        events_processed = len(events)
        teams_upserted = len(stats)

        leaderboard = sorted(stats, key=lambda item: item.ts, reverse=True)
        for t in leaderboard:
            print(
                f"{t.team_num}: matches={t.matches_played}, opr={t.opr:.2f}, dpr={t.dpr:.2f}, ccwm={t.ccwm:.2f}, ts={t.ts:.2f}, tsRank={t.ts_rank}, mu={t.ts_mu:.2f}, sigma={t.ts_sigma:.2f}"
            )

        complete_refresh_run(
            engine,
            run_id=run_id,
            status="succeeded",
            events_processed=events_processed,
            teams_upserted=teams_upserted,
        )

        logger.info("Processed %s events and upserted %s teams.", events_processed, teams_upserted)
        return events_processed
    except Exception as exc:
        complete_refresh_run(
            engine,
            run_id=run_id,
            status="failed",
            events_processed=events_processed,
            teams_upserted=teams_upserted,
            error_message=str(exc)[:2048],
        )
        raise


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--season-backfill",
        type=int,
        help="Manually compute stats for all events in the given season.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )
    if args.season_backfill is not None:
        await update_events(
            season_id=args.season_backfill,
            include_entire_season=True,
        )
        return

    await update_events()


if __name__ == "__main__":
    asyncio.run(main())
