import pytest

import db


def test_get_engine_from_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")

    engine = db.get_engine()

    assert engine.url.drivername == "sqlite+pysqlite"


def test_get_engine_requires_fallback_parts(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DB_USER", raising=False)
    monkeypatch.delenv("DB_PASS", raising=False)
    monkeypatch.delenv("DB_HOST", raising=False)
    monkeypatch.delenv("DB_NAME", raising=False)

    with pytest.raises(RuntimeError, match="Database connection is not configured"):
        db.get_engine()
