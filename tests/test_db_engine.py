import pytest

import db


def test_get_engine_from_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")

    engine = db.get_engine()

    assert engine.url.drivername == "sqlite+pysqlite"


def test_get_engine_requires_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL is not set"):
        db.get_engine()


def test_get_engine_sets_a_bounded_pool_for_postgres(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@h/d")

    engine = db.get_engine()

    assert engine.url.drivername == "postgresql+psycopg"
    assert engine.pool.size() == 5
