from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class TeamProfile:
    team_id: int
    team_num: str
    team_name: str | None
    grade: str | None
    region: str | None

    @staticmethod
    def from_json(payload: dict[str, Any]) -> "TeamProfile":
        location = payload.get("location") or {}
        return TeamProfile(
            team_id=int(payload["id"]),
            team_num=str(payload["number"]),
            team_name=payload.get("team_name"),
            grade=payload.get("grade"),
            region=location.get("region"),
        )
