from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class Event:
    id: int
    sku: str
    name: str
    start: datetime
    end: datetime
    season_id: int
    divisions_id: list[int]

    @staticmethod
    def from_json(payload: dict[str, Any]) -> "Event":
        return Event(
            id=int(payload["id"]),
            sku=str(payload["sku"]),
            name=str(payload["name"]),
            start=datetime.fromisoformat(payload["start"]),
            end=datetime.fromisoformat(payload["end"]),
            season_id=int(payload["season"]["id"]),
            divisions_id=[int(division["id"]) for division in payload["divisions"]],
        )
