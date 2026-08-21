from datetime import datetime

from config import DEFAULT_EVENT_START, load_app_config


def test_load_app_config_defaults(monkeypatch):
    monkeypatch.delenv("VEX_SEASON_ID", raising=False)
    monkeypatch.delenv("VEX_EVENT_START", raising=False)

    cfg = load_app_config()

    assert cfg.season_id is None
    assert cfg.event_start == DEFAULT_EVENT_START


def test_load_app_config_custom(monkeypatch):
    monkeypatch.setenv("VEX_SEASON_ID", "190")
    monkeypatch.setenv("VEX_EVENT_START", "2026-01-01T12:00:00")

    cfg = load_app_config()

    assert cfg.season_id == 190
    assert cfg.event_start == datetime(2026, 1, 1, 12, 0, 0)
