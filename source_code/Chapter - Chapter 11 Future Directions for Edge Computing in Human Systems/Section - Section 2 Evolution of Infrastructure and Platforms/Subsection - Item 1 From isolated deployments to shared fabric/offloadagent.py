#!/usr/bin/env python3
# offload_agent.py - runtime policy deciding local vs remote processing.
import asyncio
import aiohttp
import psutil
import time
from typing import List, Tuple

# Configure peers and weights (real deployments use service discovery)
PEERS: List[Tuple[str, float, float]] = [
    # (url, mu_estimate_tasks_per_s, energy_cost_per_task_joule)
    ("http://10.0.1.2:8080/process", 50.0, 0.8),
    ("http://10.0.1.3:8080/process", 80.0, 1.2),
]
LOCAL_MU = 20.0   # local processing rate estimate
LOCAL_E = 0.5     # local energy per task (J)

ALPHA = 1.0  # latency weight
BETA = 0.1   # energy weight

async def rtt(session: aiohttp.ClientSession, url: str) -> float:
    start = time.time()
    try:
        async with session.get(url, timeout=1) as resp:
            await resp.read()
    except Exception:
        return 2.0  # large RTT if unreachable
    return time.time() - start

def cpu_load_cost() -> float:
    # Model: effective service rate linearly degrades with CPU load
    load = psutil.cpu_percent(interval=None) / 100.0
    mu_eff = max(1.0, LOCAL_MU * (1.0 - load))
    # estimated processing latency
    latency = 1.0 / mu_eff
    return latency, LOCAL_E

async def choose_target(session: aiohttp.ClientSession) -> str:
    local_latency, local_energy = cpu_load_cost()
    best = ("local", ALPHA*local_latency + BETA*local_energy, None)
    for url, mu, e in PEERS:
        r = await rtt(session, url)
        # use a conservative queueing approximation
        latency = r + 1.0 / max(1e-3, mu*0.8)  # reserve headroom
        cost = ALPHA*latency + BETA*e
        if cost < best[1]:
            best = (url, cost, latency)
    return best[0]

async def process_task(task_payload: bytes):
    async with aiohttp.ClientSession() as session:
        target = await choose_target(session)
        if target == "local":
            # local synchronous processing (placeholder)
            await asyncio.sleep(0.01)  # simulate work
            return {"processed_by": "local"}
        else:
            async with session.post(target, data=task_payload, timeout=5) as resp:
                return await resp.json()

# Example event loop hook
async def main_loop():
    while True:
        # fetch task from local queue or sensor (placeholder)
        task = b"image bytes"
        result = await process_task(task)
        # emit result to bus or actuator
        await asyncio.sleep(0.005)

if __name__ == "__main__":
    asyncio.run(main_loop())