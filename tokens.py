import itertools
import os

tokens_str = os.getenv("RE_TOKENS", "")
TOKENS = [token.strip() for token in tokens_str.split(",") if token.strip()]
if not TOKENS:
    raise RuntimeError("RE_TOKENS is required and must contain at least one token.")

token_cycle = itertools.cycle(TOKENS)


def get_token():
    return next(token_cycle)
