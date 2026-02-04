from enum import Enum

class Grade(Enum):
    MS = "Middle School"
    HS = "High School"
    CO = "College"

class TeamStats:
    team_id = None
    team_num = 0
    team_name = None
    grade = Grade.HS
    region = None

    total_matches = 0
    total_wins = 0
    total_losses = 0
    total_draws = 0
    total_winrate = 0

    qual_wins = 0
    qual_losses = 0
    qual_draws = 0
    qual_winrate = 0

    elim_wins = 0
    elim_losses = 0
    elim_draws = 0
    elim_winrate = 0

    skills_prog = 0
    skills_driver = 0
    skills_total = 0
    skills_global_rank = 0
    skills_region_rank = 0

    avg_ap = 0
    avg_awp = 0
    avg_match_wp = 0

    opr = 0
    dpr = 0
    ccwm = 0

    ts = 0
    ts_rank = 0
    ts_mu = 0
    ts_sigma = 0

    qualed_worlds = False
    qualed_regionals = False

    unqualed_worlds_skills_global_rank = 0
    unqualed_regionals_skills_region_rank = 0

    def __init__(self, team_id, number):
        self.team_id = team_id
        self.team_num = number

    def __repr__(self):
        return f'{self.team_id.number}: matches={self.matches_played}'

    def __eq__(self, other):
        if isinstance(other, TeamStats):
            return self.team_id == other.team_id
        return False

    def update_opr(self, new_opr, num_matches):
        t = num_matches / (num_matches + self.matches_played)
        self.opr = self.opr * (1 - t) + new_opr * t
        self.ccwm = self.opr - self.dpr

    def update_dpr(self, new_dpr, num_matches):
        t = num_matches / (num_matches + self.matches_played)
        self.dpr = self.dpr * (1 - t) + new_dpr * t
        self.ccwm = self.opr - self.dpr