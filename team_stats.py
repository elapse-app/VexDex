from enum import Enum

class Grade(Enum):
    MS = "Middle School"
    HS = "High School"
    CO = "College"

class TeamId:
    id = 0
    number = ""
    team_name = ""
    grade = Grade.HS

    def __init__(self, id, number):
        self.id = id
        self.number = number

    def __eq__(self, other):
        if isinstance(other, TeamId):
            return self.id == other.id
        return False

class Stats:
    matches_played = 0

    skills_prog = 0
    skills_driver = 0
    skills_total = 0
    skills_rank = 0

    opr = 0
    dpr = 0
    ccwm = 0

    ts = 0
    ts_rank = 0
    ts_mu = 0
    ts_sigma = 0

    def update_opr(self, new_opr, num_matches):
        t = num_matches / (num_matches + self.matches_played)
        self.opr = self.opr * (1 - t) + new_opr * t
        self.ccwm = self.opr - self.dpr

    def update_dpr(self, new_dpr, num_matches):
        t = num_matches / (num_matches + self.matches_played)
        self.dpr = self.dpr * (1 - t) + new_dpr * t
        self.ccwm = self.opr - self.dpr

class TeamStats:
    team_id = None

    matches_played = 0

    skills_prog = 0
    skills_driver = 0
    skills_total = 0
    skills_rank = 0

    opr = 0
    dpr = 0
    ccwm = 0

    ts = 0
    ts_rank = 0
    ts_mu = 0
    ts_sigma = 0

    # tournament_stats = Stats()
    # season_stats = Stats()

    def __init__(self, team_id, number):
        self.team_id = TeamId(team_id, number)

    def __repr__(self):
        return f'{self.team_id.number}: matches={self.matches_played}'

    def __eq__(self, other):
        if isinstance(other, TeamStats):
            return self.team_id == other.team_id
        return False