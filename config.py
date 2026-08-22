from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from os import getenv


@dataclass(frozen=True)
class AppConfig:
    season_id: int | None
    event_start: datetime


DEFAULT_EVENT_START = datetime(2025, 12, 17, tzinfo=UTC)


def load_app_config() -> AppConfig:
    season_raw = getenv("VEX_SEASON_ID")
    season_id = int(season_raw) if season_raw else None

    start_raw = getenv("VEX_EVENT_START")
    if start_raw:
        event_start = datetime.fromisoformat(start_raw)
        # The VEX Events API returns offset-aware timestamps; a naive override
        # here would break comparisons against them, so assume UTC if unspecified.
        if event_start.tzinfo is None:
            event_start = event_start.replace(tzinfo=UTC)
    else:
        event_start = DEFAULT_EVENT_START

    return AppConfig(
        season_id=season_id,
        event_start=event_start,
    )
