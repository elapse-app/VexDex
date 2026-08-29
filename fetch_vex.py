from __future__ import annotations

import asyncio
import logging
import random
import sys
from typing import Any

from playwright.async_api import APIRequestContext, Playwright, async_playwright

import rate_limiter
import tokens

logger = logging.getLogger(__name__)

_playwright: Playwright | None = None
_request_context: APIRequestContext | None = None
_init_lock = asyncio.Lock()

# Bounds total concurrent in-flight HTTP requests across the whole process.
# A full-season backfill fans fetch_data() out across every event at once
# (see update_stats.py), so this has to be a single shared limiter rather
# than a semaphore created fresh per fetch_data() call — a per-call semaphore
# only bounds pagination within that one call's own endpoint, not how many
# fetch_data() calls run concurrently across different events.
_REQUEST_SEMAPHORE = asyncio.Semaphore(15)


def _jittered_sleep(seconds: float) -> float:
    """Adds upward-only jitter so concurrent coroutines that got rate-limited
    at the same moment don't all retry in lockstep. Never returns less than
    `seconds` — the server-mandated (or backed-off) wait is always honored."""
    return seconds * random.uniform(1.0, 1.3)


async def _get_request_context() -> APIRequestContext:
    """Lazily start one Playwright driver + request context and reuse it for
    every call. Starting a fresh async_playwright() instance per request (the
    old behavior) launches a whole separate browser-driver subprocess for
    every single HTTP call, which explodes to thousands of processes during a
    season backfill and can crash the host."""
    global _playwright, _request_context
    async with _init_lock:
        if _request_context is None:
            logger.debug("Starting new Playwright driver + request context.")
            _playwright = await async_playwright().start()
            _request_context = await _playwright.request.new_context()
    return _request_context


async def _discard_request_context(dead_context: APIRequestContext) -> None:
    """Drop the shared context so the next caller starts a fresh driver. Only
    acts if `dead_context` is still the cached one — otherwise some other
    caller already recovered it, and clobbering that fresh context would
    undo the recovery."""
    global _playwright, _request_context
    async with _init_lock:
        if _request_context is not dead_context:
            return
        logger.debug("Discarding dead request context; next request will start a fresh driver.")
        dead_playwright = _playwright
        _request_context = None
        _playwright = None
    if dead_playwright is not None:
        try:
            await dead_playwright.stop()
        except Exception:
            pass


async def close() -> None:
    """Tear down the shared Playwright request context. Call once, after all
    fetch_data() calls for a run have completed."""
    global _playwright, _request_context
    if _request_context is not None:
        await _request_context.dispose()
        _request_context = None
    if _playwright is not None:
        await _playwright.stop()
        _playwright = None


async def fetch_data(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    default_backoff: int = 5,
    max_backoff: int = 120,
) -> list[dict[str, Any]] | dict[str, Any]:
    if params is None:
        params = {}

    logger.debug("fetch_data: requesting %s (params=%s)", url, params)
    first_pg = await get(url, params, 1, default_backoff, max_backoff)
    if "meta" not in first_pg:
        logger.debug("fetch_data: %s returned a non-paginated payload", url)
        return first_pg
    last_pg_num = first_pg["meta"]["last_page"]
    logger.debug("fetch_data: %s has %s page(s)", url, last_pg_num)

    tasks = [get(url, params, pg, default_backoff, max_backoff) for pg in range(2, last_pg_num + 1)]
    data_pgs = await asyncio.gather(*tasks)

    data = first_pg["data"]
    for pg in data_pgs:
        data += pg["data"]

    logger.debug("fetch_data: %s complete, %s item(s) across %s page(s)", url, len(data), last_pg_num)
    return data


async def get(url, params, pg, default_backoff, max_backoff):
    backoff = default_backoff
    attempt = 0
    logger.debug("get: waiting for a request slot url=%s page=%s", url, pg)
    async with _REQUEST_SEMAPHORE:
        while True:
            attempt += 1
            # Re-fetched every attempt: if the driver died since the last
            # attempt, this picks up the freshly-recreated context instead of
            # retrying forever against the dead one.
            request_context = await _get_request_context()
            token = tokens.get_token()
            await rate_limiter.acquire()
            logger.debug(
                "get: attempt %s url=%s page=%s token=...%s",
                attempt, url, pg, token[-4:],
            )
            try:
                res = await request_context.get(
                    url,
                    params=params | {"page": pg},
                    headers={
                        "Authorization": f"Bearer {token}",
                    },
                )
            except Exception as e:
                logger.warning("Error fetching page %s: %s", pg, e)
                await _discard_request_context(request_context)
                sleep_for = _jittered_sleep(backoff)
                logger.debug(
                    "get: sleeping %.1fs (base %ss) before retry (transport error)",
                    sleep_for, backoff,
                )
                await asyncio.sleep(sleep_for)
                backoff = min(2 * backoff, max_backoff)
                continue

            logger.debug("get: response url=%s page=%s status=%s", url, pg, res.status)

            if res.status == 429:
                # The API can send retry-after: 0 (e.g. a per-token
                # concurrency limit rather than a time-window one, which has
                # no meaningful wait time). Trusting that verbatim turns this
                # into a zero-delay busy loop that hammers the endpoint
                # forever without ever making progress, so floor it at the
                # current backoff and keep that backoff escalating.
                retry_after = max(int(res.headers.get("retry-after", backoff)), backoff)
                tokens.mark_rate_limited(token, retry_after)
                sleep_for = _jittered_sleep(retry_after)
                print(
                    f"Rate Limited: Retrying page {pg} after {sleep_for:.1f}s "
                    f"(base {retry_after}s; url={url}, token=...{token[-4:]}, attempt={attempt})",
                    file=sys.stderr,
                )
                await asyncio.sleep(sleep_for)
                backoff = min(2 * backoff, max_backoff)
                continue

            if 500 <= res.status < 600:
                logger.warning("Server error %s on page %s, retrying", res.status, pg)
                sleep_for = _jittered_sleep(backoff)
                logger.debug(
                    "get: sleeping %.1fs (base %ss) before retry (server error)",
                    sleep_for, backoff,
                )
                await asyncio.sleep(sleep_for)
                backoff = min(2 * backoff, max_backoff)
                continue

            if res.status >= 400:
                # Client errors (404, 401, ...) won't fix themselves on retry —
                # failing fast beats retrying forever with no way to succeed.
                body = await res.text()
                raise RuntimeError(f"HTTP {res.status} fetching {url} (page {pg}): {body[:200]}")

            return await res.json()
