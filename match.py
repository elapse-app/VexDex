import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


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
    played: bool

    @staticmethod
    def _alliance_team_ids(alliance: dict[str, Any]) -> list[int] | None:
        """Every downstream computation (OPR/DPR, TrueSkill) hard-assumes
        exactly 2 teams per alliance, indexed [0]/[1] — so an alliance that
        doesn't have exactly 2 resolvable team ids can't be scored at all.
        Returns None rather than raising: the API has been observed to
        return matches with an empty/partial `teams` list (e.g. an
        elimination bracket slot that hasn't been paired yet), and one
        malformed match shouldn't take down the whole event."""
        teams = alliance.get("teams") or []
        if len(teams) != 2:
            return None
        ids: list[int] = []
        for t in teams:
            team = t.get("team") if isinstance(t, dict) else None
            if not team or team.get("id") is None:
                return None
            ids.append(int(team["id"]))
        return ids

    @staticmethod
    def from_json(payload: dict[str, Any]) -> "Match | None":
        alliances = payload.get("alliances") or []
        if len(alliances) != 2:
            logger.warning("Skipping match %s: expected 2 alliances, got %s", payload.get("id"), len(alliances))
            return None

        red_teams = Match._alliance_team_ids(alliances[0])
        blue_teams = Match._alliance_team_ids(alliances[1])
        if red_teams is None or blue_teams is None:
            logger.warning("Skipping match %s: alliance team data incomplete", payload.get("id"))
            return None

        return Match(
            id=int(payload["id"]),
            match_num=int(payload["matchnum"]),
            instance=int(payload["instance"]),
            match_type=MatchType(payload["round"]),
            red_teams=red_teams,
            blue_teams=blue_teams,
            red_score=int(alliances[0]["score"]),
            blue_score=int(alliances[1]["score"]),
            # A scheduled match that hasn't happened yet still appears here
            # with score 0-0 — "started" is null until the match actually
            # runs. (The API's own "scored" field is not a reliable signal:
            # it's false even on matches with real, final scores.)
            played=payload.get("started") is not None,
        )
