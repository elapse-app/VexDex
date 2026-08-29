import importlib
import sys

import pytest


def _reload_tokens_module():
    if "tokens" in sys.modules:
        del sys.modules["tokens"]
    return importlib.import_module("tokens")


def test_tokens_parse(monkeypatch):
    monkeypatch.setenv("VEX_TOKENS", "a,b , c")

    tokens = _reload_tokens_module()

    assert tokens.TOKENS == ["a", "b", "c"]


def test_tokens_required(monkeypatch):
    monkeypatch.setenv("VEX_TOKENS", "")

    with pytest.raises(RuntimeError, match="VEX_TOKENS is required"):
        _reload_tokens_module()


def test_get_token_skips_cooling_down_token(monkeypatch):
    monkeypatch.setenv("VEX_TOKENS", "a,b")
    tokens = _reload_tokens_module()

    clock = [100.0]
    monkeypatch.setattr(tokens.time, "monotonic", lambda: clock[0])

    tokens.mark_rate_limited("a", cooldown_seconds=10)

    # Round-robin would normally alternate a, b, a, b, ... — but "a" is
    # cooling down, so every draw should land on "b" instead.
    seen = {tokens.get_token() for _ in range(4)}
    assert seen == {"b"}


def test_get_token_becomes_available_again_after_cooldown_expires(monkeypatch):
    monkeypatch.setenv("VEX_TOKENS", "a,b")
    tokens = _reload_tokens_module()

    clock = [100.0]
    monkeypatch.setattr(tokens.time, "monotonic", lambda: clock[0])

    tokens.mark_rate_limited("a", cooldown_seconds=10)
    assert tokens.get_token() == "b"

    clock[0] = 111.0  # cooldown (until 110.0) has elapsed
    seen = {tokens.get_token() for _ in range(4)}
    assert "a" in seen


def test_get_token_falls_back_to_soonest_expiring_when_all_cooling_down(monkeypatch):
    monkeypatch.setenv("VEX_TOKENS", "a,b")
    tokens = _reload_tokens_module()

    clock = [100.0]
    monkeypatch.setattr(tokens.time, "monotonic", lambda: clock[0])

    tokens.mark_rate_limited("a", cooldown_seconds=20)
    tokens.mark_rate_limited("b", cooldown_seconds=5)

    assert tokens.get_token() == "b"
