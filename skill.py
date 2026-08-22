from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class SkillRun:
    team_id: int
    skill_type: str  # "driver" or "programming"
    score: int
    attempts: int
    event_rank: int

    @staticmethod
    def from_json(payload: dict[str, Any]) -> "SkillRun":
        # attempts is null (not 0) when a team registered for skills but never
        # actually ran — score/rank are still real integers in that case.
        return SkillRun(
            team_id=int(payload["team"]["id"]),
            skill_type=str(payload["type"]),
            score=int(payload["score"]),
            attempts=int(payload["attempts"] or 0),
            event_rank=int(payload["rank"]),
        )
