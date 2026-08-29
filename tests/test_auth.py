"""Unit tests for the DB-backed API token helpers in db.py."""

import os

import pytest

import db


@pytest.fixture
def engine(monkeypatch):
    db_url = os.getenv("TEST_DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("DATABASE_URL", db_url)
    eng = db.get_engine()
    db.ensure_schema(eng)
    try:
        yield eng
    finally:
        db.Base.metadata.drop_all(eng)


def test_hash_token_is_deterministic_hex():
    h1 = db._hash_token("abc")
    h2 = db._hash_token("abc")
    assert h1 == h2
    assert len(h1) == 64
    assert int(h1, 16) >= 0  # valid hex
    assert db._hash_token("abc") != db._hash_token("abd")


def test_create_api_token_persists_only_the_hash(engine):
    raw = db.create_api_token(engine, "frontend")

    assert isinstance(raw, str) and len(raw) > 20
    tokens = db.list_api_tokens(engine)
    assert len(tokens) == 1
    assert tokens[0].label == "frontend"
    assert tokens[0].token_hash == db._hash_token(raw)
    assert tokens[0].token_hash != raw  # raw value is never stored


def test_verify_api_token_accepts_valid_and_rejects_unknown(engine):
    raw = db.create_api_token(engine, "frontend")

    assert db.verify_api_token(engine, raw) is not None
    assert db.verify_api_token(engine, "not-a-real-token") is None


def test_verify_api_token_sets_last_used_at(engine):
    raw = db.create_api_token(engine, "frontend")
    assert db.list_api_tokens(engine)[0].last_used_at is None

    db.verify_api_token(engine, raw)

    assert db.list_api_tokens(engine)[0].last_used_at is not None


def test_revoked_token_is_rejected(engine):
    raw = db.create_api_token(engine, "frontend")
    token_id = db.list_api_tokens(engine)[0].token_id

    revoked = db.revoke_api_token(engine, token_id=token_id)

    assert revoked == 1
    assert db.verify_api_token(engine, raw) is None
    # Revoking again is a no-op (already revoked, not re-counted).
    assert db.revoke_api_token(engine, token_id=token_id) == 0


def test_revoke_by_label_revokes_all_matching(engine):
    db.create_api_token(engine, "frontend")
    db.create_api_token(engine, "frontend")
    db.create_api_token(engine, "cron")

    assert db.revoke_api_token(engine, label="frontend") == 2
    active = [t for t in db.list_api_tokens(engine) if t.revoked_at is None]
    assert [t.label for t in active] == ["cron"]


def test_revoke_requires_exactly_one_selector(engine):
    with pytest.raises(ValueError):
        db.revoke_api_token(engine)
    with pytest.raises(ValueError):
        db.revoke_api_token(engine, token_id=1, label="frontend")
