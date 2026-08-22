from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class Award:
    title: str
    qualifications: list[str]
    team_ids: list[int]

    @staticmethod
    def from_json(payload: dict[str, Any]) -> "Award":
        return Award(
            title=str(payload["title"]),
            qualifications=[str(q) for q in payload.get("qualifications") or []],
            team_ids=[int(winner["team"]["id"]) for winner in payload.get("teamWinners") or []],
        )

    @property
    def qualifies_worlds(self) -> bool:
        return "World Championship" in self.qualifications

    @property
    def qualifies_regionals(self) -> bool:
        return any(q != "World Championship" for q in self.qualifications)
