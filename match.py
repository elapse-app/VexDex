from dataclasses import dataclass
from enum import Enum
from typing import Any


class MatchType(Enum):
    PRAC = 1
    QUAL = 2
    ELIM = 3

    @classmethod
    def _missing_(cls, value):
        return cls.ELIM


@dataclass(slots=True)
class Match:
    id: int
    match_num: int
    instance: int
    match_type: MatchType
    red_teams: list[int]
    blue_teams: list[int]
    red_score: int
    blue_score: int

    @staticmethod
    def from_json(payload: dict[str, Any]) -> "Match":
        return Match(
            id=int(payload["id"]),
            match_num=int(payload["matchnum"]),
            instance=int(payload["instance"]),
            match_type=MatchType(payload["round"]),
            red_teams=[
                int(payload["alliances"][0]["teams"][0]["team"]["id"]),
                int(payload["alliances"][0]["teams"][1]["team"]["id"]),
            ],
            blue_teams=[
                int(payload["alliances"][1]["teams"][0]["team"]["id"]),
                int(payload["alliances"][1]["teams"][1]["team"]["id"]),
            ],
            red_score=int(payload["alliances"][0]["score"]),
            blue_score=int(payload["alliances"][1]["score"]),
        )
