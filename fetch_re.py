import sys
import asyncio
from playwright.async_api import async_playwright
import tokens

async def fetch_data(url, *, params=None, max_concurrency = 15, default_backoff = 5, max_backoff = 120):
    if params is None:
        params = {}

    semaphore = asyncio.Semaphore(max_concurrency)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        first_pg = await get(url, params, 1, semaphore, page, default_backoff, max_backoff)
        if not 'meta' in first_pg.keys():
            await browser.close()
            return first_pg
        last_pg_num = first_pg['meta']['last_page']

        tasks = [get(url, params, pg, semaphore, page, default_backoff, max_backoff) for pg in range(2, last_pg_num + 1)]
        data_pgs = await asyncio.gather(*tasks)

        data = first_pg['data']
        for pg in data_pgs:
            data += pg['data']

        await browser.close()

        return data

async def get(url, params, pg, semaphore, page, default_backoff, max_backoff):
    backoff = default_backoff
    async with semaphore:
        while True:
            token = tokens.get_token()
            try:
                res = await page.request.get(
                    url,
                    params=params | {"page": pg},
                    headers={
                        "Authorization": f"Bearer {token}",
                    }
                )

                err, delay = await handle_error(res, pg, backoff)
                if err:
                    await asyncio.sleep(delay)
                    backoff = min(delay * 2, max_backoff)
                    continue

                data = await res.json()
                # print(json.dumps(data, indent=2))
                return data
            except Exception as e:
                print(f"Error fetching page {pg}: {e}")
                await asyncio.sleep(backoff)
                backoff = min(2 * backoff, max_backoff)


async def handle_error(res, pg, backoff):
    if res.status == 429:
        retry_after = int(res.headers.get("retry-after", backoff))
        print(
            f"Rate Limited: Retrying page {pg} after {retry_after}s",
            file=sys.stderr)
        return True, retry_after
    if res.status >= 400:
        print(f"HTTP error {res.status} on page {pg}")
        return True, backoff

    return False, 0