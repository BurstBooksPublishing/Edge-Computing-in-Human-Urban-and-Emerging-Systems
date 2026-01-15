#!/usr/bin/env python3
"""
Prefetch scheduler for an edge node. Durable metadata in SQLite.
Works with local NGINX reverse proxy cache.
"""
import asyncio
import aiohttp
import sqlite3
from pathlib import Path

DB_PATH = Path("/var/lib/edge_cache/meta.db")
MANIFEST_URL = "https://origin.example/events/manifest.json"
NGINX_PREFETCH_URL = "http://127.0.0.1:8080/cache_fetch"  # endpoint that forces cache fill
STORAGE_B = 5 * 1024**3  # bytes storage budget (5 GiB)
PREFETCH_RATE_R = 10 * 1024**2  # bytes/sec prefetch cap (10 MiB/s)
CONCURRENCY = 6

# persistent metadata
conn = sqlite3.connect(DB_PATH)
conn.execute("CREATE TABLE IF NOT EXISTS items(id TEXT PRIMARY KEY, size INT, p REAL, fetched INT)")
conn.commit()

async def fetch_manifest(session):
    async with session.get(MANIFEST_URL, timeout=10) as r:
        r.raise_for_status()
        return await r.json()

def select_candidates(items, budget):
    # density = p * deltaL / size; deltaL treated uniform here for simplicity
    items_sorted = sorted(items, key=lambda it: (it["p"]/it["size"]), reverse=True)
    chosen, used = [], 0
    for it in items_sorted:
        if used + it["size"] > budget:
            continue
        chosen.append(it)
        used += it["size"]
    return chosen

async def prefetch_item(session, item, sem):
    async with sem:
        # trigger local proxy fetch which stores in cache; include origin URL
        params = {"url": item["url"]}
        async with session.get(NGINX_PREFETCH_URL, params=params, timeout=30) as r:
            r.raise_for_status()
            # record metadata
            conn.execute("INSERT OR REPLACE INTO items VALUES(?,?,?,1)",
                         (item["id"], item["size"], item["p"]))
            conn.commit()

async def main():
    sem = asyncio.Semaphore(CONCURRENCY)
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        manifest = await fetch_manifest(session)
        candidates = select_candidates(manifest["segments"], STORAGE_B)
        tasks = [prefetch_item(session, it, sem) for it in candidates]
        await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.run(main())