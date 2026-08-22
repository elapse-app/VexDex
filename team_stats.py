from dataclasses import dataclass, field


@dataclass(slots=True)
class TeamStats:
    """One team's result at one event. Everything here is scoped to a single
    event — season aggregates are computed separately from a history of these."""

    team_id: int
    team_num: str

    total_matches: int = 0
    total_wins: int = 0
    total_losses: int = 0
    total_draws: int = 0

    qual_matches: int = 0
    qual_wins: int = 0
    qual_losses: int = 0
    qual_draws: int = 0

    elim_matches: int = 0
    elim_wins: int = 0
    elim_losses: int = 0
    elim_draws: int = 0

    # Cumulative ranking-tiebreaker points for this event, straight from the
    # rankings payload (qual-match scope): win points, autonomous points,
    # strength-of-schedule points.
    wp: int = 0
    ap: int = 0
    sp: int = 0
    average_match_score: float = 0.0
    high_score: int = 0

    opr: float = 0.0
    dpr: float = 0.0
    ccwm: float = 0.0

    ts: float = 0.0
    ts_rank: int = 0
    ts_mu: float = 0.0
    ts_sigma: float = 0.0

    # Skills scores at this event, if the team ran skills (None if they didn't).
    skills_driver: int | None = None
    skills_prog: int | None = None

    # Award titles won by this team at this event, with their qualification
    # grants (e.g. ["World Championship"]) — empty list means no qualifying award.
    awards: list[tuple[str, list[str]]] = field(default_factory=list)

    @property
    def matches_played(self) -> int:
        return self.total_matches

    @property
    def total_winrate(self) -> float:
        return _win_rate(self.total_wins, self.total_losses, self.total_draws)

    @property
    def qual_winrate(self) -> float:
        return _win_rate(self.qual_wins, self.qual_losses, self.qual_draws)

    @property
    def elim_winrate(self) -> float:
        return _win_rate(self.elim_wins, self.elim_losses, self.elim_draws)

    @property
    def avg_ap(self) -> float:
        return self.ap / self.qual_matches if self.qual_matches else 0.0

    @property
    def avg_wp(self) -> float:
        return self.wp / self.qual_matches if self.qual_matches else 0.0

    @property
    def avg_awp(self) -> float:
        if not self.qual_matches:
            return 0.0
        return (self.wp - 2 * self.qual_wins - self.qual_draws) / self.qual_matches

    @property
    def skills_total(self) -> int | None:
        if self.skills_driver is None and self.skills_prog is None:
            return None
        return (self.skills_driver or 0) + (self.skills_prog or 0)

    @property
    def qualed_worlds(self) -> bool:
        return any("World Championship" in quals for _, quals in self.awards)

    @property
    def qualed_regionals(self) -> bool:
        return any(any(q != "World Championship" for q in quals) for _, quals in self.awards)

    def __repr__(self) -> str:
        return f"{self.team_num}: matches={self.total_matches}"


def _win_rate(wins: int, losses: int, draws: int) -> float:
    total = wins + losses + draws
    if total == 0:
        return 0.0
    return (wins + 0.5 * draws) / total
