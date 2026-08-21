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
