from enum import Enum

class MatchType(Enum):
    PRAC = 1
    QUAL = 2
    ELIM = 3

    @classmethod
    def _missing_(cls, value):
        return cls.ELIM

class Match:
    id = 0
    match_num = 0
    instance = 0
    match_type = MatchType.QUAL

    red_teams = []
    blue_teams = []

    red_score = 0
    blue_score = 0

    def __init__(self, json):
        self.id = json["id"]
        self.match_num = json["matchnum"]
        self.instance = json["instance"]
        self.match_type = MatchType(json["round"])

        self.red_teams = [json["alliances"][0]["teams"][0]["team"]["id"], json["alliances"][0]["teams"][1]["team"]["id"]]
        self.blue_teams = [json["alliances"][1]["teams"][0]["team"]["id"], json["alliances"][1]["teams"][1]["team"]["id"]]

        self.red_score = json["alliances"][0]["score"]
        self.blue_score = json["alliances"][1]["score"]