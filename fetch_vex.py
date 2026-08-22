from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any

from playwright.async_api import async_playwright

import tokens

logger = logging.getLogger(__name__)


async def fetch_data(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    max_concurrency: int = 15,
    default_backoff: int = 5,
    max_backoff: int = 120,
) -> list[dict[str, Any]] | dict[str, Any]:
    if params is None:
        params = {}

    semaphore = asyncio.Semaphore(max_concurrency)
    async with async_playwright() as p:
        request_context = await p.request.new_context()

        first_pg = await get(
            url,
            params,
            1,
            semaphore,
            request_context,
            default_backoff,
            max_backoff,
        )
        if "meta" not in first_pg:
            await request_context.dispose()
            return first_pg
        last_pg_num = first_pg["meta"]["last_page"]

        tasks = [
            get(url, params, pg, semaphore, request_context, default_backoff, max_backoff)
            for pg in range(2, last_pg_num + 1)
        ]
        data_pgs = await asyncio.gather(*tasks)

        data = first_pg["data"]
        for pg in data_pgs:
            data += pg["data"]

        await request_context.dispose()

        return data


async def get(url, params, pg, semaphore, request_context, default_backoff, max_backoff):
    backoff = default_backoff
    async with semaphore:
        while True:
            token = tokens.get_token()
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
                await asyncio.sleep(backoff)
                backoff = min(2 * backoff, max_backoff)
                continue

            if res.status == 429:
                retry_after = int(res.headers.get("retry-after", backoff))
                print(f"Rate Limited: Retrying page {pg} after {retry_after}s", file=sys.stderr)
                await asyncio.sleep(retry_after)
                backoff = min(retry_after * 2, max_backoff)
                continue

            if 500 <= res.status < 600:
                logger.warning("Server error %s on page %s, retrying", res.status, pg)
                await asyncio.sleep(backoff)
                backoff = min(2 * backoff, max_backoff)
                continue

            if res.status >= 400:
                # Client errors (404, 401, ...) won't fix themselves on retry —
                # failing fast beats retrying forever with no way to succeed.
                body = await res.text()
                raise RuntimeError(f"HTTP {res.status} fetching {url} (page {pg}): {body[:200]}")

            return await res.json()
