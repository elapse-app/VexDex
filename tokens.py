import os
import itertools

tokens_str = os.getenv("RE_TOKENS")
TOKENS = tokens_str.split(',')
token_cycle = itertools.cycle(TOKENS)

def get_token():
    return next(token_cycle)