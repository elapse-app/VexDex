from dataclasses import dataclass
from enum import Enum


class Grade(Enum):
    MS = "Middle School"
    HS = "High School"
    CO = "College"


@dataclass(slots=True)
class TeamStats:
    team_id: int
    team_num: str
    team_name: str | None = None
    grade: Grade = Grade.HS
    region: str | None = None

    total_matches: int = 0
    total_wins: int = 0
    total_losses: int = 0
    total_draws: int = 0
    total_winrate: float = 0.0

    qual_wins: int = 0
    qual_losses: int = 0
    qual_draws: int = 0
    qual_winrate: float = 0.0

    elim_wins: int = 0
    elim_losses: int = 0
    elim_draws: int = 0
    elim_winrate: float = 0.0

    skills_prog: int = 0
    skills_driver: int = 0
    skills_total: int = 0
    skills_global_rank: int = 0
    skills_region_rank: int = 0

    avg_ap: float = 0.0
    avg_awp: float = 0.0
    avg_match_wp: float = 0.0

    opr: float = 0.0
    dpr: float = 0.0
    ccwm: float = 0.0

    ts: float = 0.0
    ts_rank: int = 0
    ts_mu: float = 0.0
    ts_sigma: float = 0.0
    matches_played: int = 0

    qualed_worlds: bool = False
    qualed_regionals: bool = False

    unqualed_worlds_skills_global_rank: int = 0
    unqualed_regionals_skills_region_rank: int = 0

    def __repr__(self) -> str:
        return f"{self.team_num}: matches={self.matches_played}"
