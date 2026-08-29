import itertools
import logging
import os
import time

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

tokens_str = os.getenv("VEX_TOKENS", "")
TOKENS = [token.strip() for token in tokens_str.split(",") if token.strip()]
if not TOKENS:
    raise RuntimeError("VEX_TOKENS is required and must contain at least one token.")

token_cycle = itertools.cycle(TOKENS)

# token -> monotonic() timestamp when it's usable again. Populated on 429s so
# a rate-limited token isn't immediately handed back out to the next caller.
_cooldown_until: dict[str, float] = {}


def mark_rate_limited(token: str, cooldown_seconds: float) -> None:
    until = time.monotonic() + max(cooldown_seconds, 0)
    _cooldown_until[token] = until
    logger.debug("Marking token ...%s in cooldown for %.1fs", token[-4:], cooldown_seconds)


def get_token():
    # Fully synchronous with no `await` inside, so this scan-and-pick runs
    # atomically with respect to every other coroutine even under concurrent
    # callers — asyncio can only switch tasks at an `await` point, and there
    # isn't one here. No lock needed.
    now = time.monotonic()
    for _ in range(len(TOKENS)):
        token = next(token_cycle)
        if _cooldown_until.get(token, 0.0) <= now:
            return token

    # Every token is cooling down: fall back to whichever recovers soonest
    # rather than blocking here — the rate limiter and request semaphore
    # already gate how fast requests actually go out.
    soonest = min(TOKENS, key=lambda t: _cooldown_until.get(t, 0.0))
    logger.debug("All tokens cooling down; falling back to soonest-expiring token.")
    return soonest
