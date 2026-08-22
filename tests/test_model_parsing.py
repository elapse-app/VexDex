from datetime import datetime, timedelta, timezone

from award import Award
from event import Event
from match import Match, MatchType
from skill import SkillRun
from team_profile import TeamProfile


def test_event_from_json_parses_fields():
    # The real API always includes a UTC offset (e.g. "-04:00"), never a naive
    # timestamp — this fixture mirrors that so parsing stays tz-aware.
    payload = {
        "id": "100",
        "sku": "RE-V5RC-26-0001",
        "name": "Unit Test Open",
        "start": "2026-01-10T09:00:00-05:00",
        "end": "2026-01-10T18:00:00-05:00",
        "season": {"id": "190"},
        "divisions": [{"id": "1"}, {"id": 2}],
    }

    event = Event.from_json(payload)

    tz = timezone(timedelta(hours=-5))
    assert event.id == 100
    assert event.sku == "RE-V5RC-26-0001"
    assert event.name == "Unit Test Open"
    assert event.start == datetime(2026, 1, 10, 9, 0, 0, tzinfo=tz)
    assert event.end == datetime(2026, 1, 10, 18, 0, 0, tzinfo=tz)
    assert event.season_id == 190
    assert event.divisions_id == [1, 2]


def test_match_from_json_and_round_fallback():
    payload = {
        "id": "55",
        "matchnum": "8",
        "instance": "1",
        "round": 99,
        "started": "2026-01-10T09:18:03-05:00",
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
    assert match.played is True


def test_match_from_json_unplayed_when_not_started():
    # A scheduled-but-not-yet-played match: real score fields present (often
    # 0-0) but "started" is null. Confirmed against live API data.
    payload = {
        "id": 1,
        "matchnum": 1,
        "instance": 1,
        "round": 2,
        "started": None,
        "alliances": [
            {"teams": [{"team": {"id": 1}}, {"team": {"id": 2}}], "score": 0},
            {"teams": [{"team": {"id": 3}}, {"team": {"id": 4}}], "score": 0},
        ],
    }

    assert Match.from_json(payload).played is False


def test_skill_run_treats_null_attempts_as_zero():
    # Live API: attempts is null (not 0) when a team registered for skills
    # but never actually ran — score/rank are still real integers.
    payload = {"team": {"id": 169748}, "type": "programming", "rank": 0, "score": 0, "attempts": None}

    run = SkillRun.from_json(payload)

    assert run.team_id == 169748
    assert run.attempts == 0
    assert run.score == 0


def test_award_qualification_rules():
    worlds_payload = {
        "title": "Excellence Award (V5)",
        "qualifications": ["World Championship"],
        "teamWinners": [{"team": {"id": 1}}, {"team": {"id": 2}}],
    }
    regional_payload = {
        "title": "Design Award (V5)",
        "qualifications": ["Event Region Championship"],
        "teamWinners": [{"team": {"id": 3}}],
    }
    no_qual_payload = {"title": "Sportsmanship Award (V5)", "qualifications": [], "teamWinners": []}

    worlds_award = Award.from_json(worlds_payload)
    regional_award = Award.from_json(regional_payload)
    no_qual_award = Award.from_json(no_qual_payload)

    assert worlds_award.team_ids == [1, 2]
    assert worlds_award.qualifies_worlds is True
    assert worlds_award.qualifies_regionals is False

    assert regional_award.qualifies_worlds is False
    assert regional_award.qualifies_regionals is True

    assert no_qual_award.qualifies_worlds is False
    assert no_qual_award.qualifies_regionals is False


def test_team_profile_from_json_parses_region():
    payload = {
        "id": 185290,
        "number": "12141A",
        "team_name": "Ctrl+Alt+Elite",
        "grade": "High School",
        "location": {"region": "Victoria", "country": "Australia"},
    }

    profile = TeamProfile.from_json(payload)

    assert profile.team_id == 185290
    assert profile.team_num == "12141A"
    assert profile.team_name == "Ctrl+Alt+Elite"
    assert profile.grade == "High School"
    assert profile.region == "Victoria"
