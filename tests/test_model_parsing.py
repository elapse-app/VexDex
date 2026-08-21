from datetime import datetime

from event import Event
from match import Match, MatchType


def test_event_from_json_parses_fields():
    payload = {
        "id": "100",
        "sku": "RE-V5RC-26-0001",
        "name": "Unit Test Open",
        "start": "2026-01-10T09:00:00",
        "end": "2026-01-10T18:00:00",
        "season": {"id": "190"},
        "divisions": [{"id": "1"}, {"id": 2}],
    }

    event = Event.from_json(payload)

    assert event.id == 100
    assert event.sku == "RE-V5RC-26-0001"
    assert event.name == "Unit Test Open"
    assert event.start == datetime(2026, 1, 10, 9, 0, 0)
    assert event.end == datetime(2026, 1, 10, 18, 0, 0)
    assert event.season_id == 190
    assert event.divisions_id == [1, 2]


def test_match_from_json_and_round_fallback():
    payload = {
        "id": "55",
        "matchnum": "8",
        "instance": "1",
        "round": 99,
        "alliances": [
            {
                "teams": [
                    {"team": {"id": "101"}},
                    {"team": {"id": "102"}},
                ],
                "score": "15",
            },
            {
                "teams": [
                    {"team": {"id": 201}},
                    {"team": {"id": 202}},
                ],
                "score": 12,
            },
        ],
    }

    match = Match.from_json(payload)

    assert match.id == 55
    assert match.match_num == 8
    assert match.instance == 1
    assert match.match_type == MatchType.ELIM
    assert match.red_teams == [101, 102]
    assert match.blue_teams == [201, 202]
    assert match.red_score == 15
    assert match.blue_score == 12
