#!/usr/bin/env python3
# monitors TCP RTT, frame_time (ms) pushed by renderer, computes visibility V,
# and notifies renderer via WebSocket for graceful degradation decisions.

import asyncio
import json
import time
import math
import websockets

EDGE_HOST = "10.0.0.2"        # edge server IP
EDGE_PORT = 8000              # measurable TCP port
WS_PORT = 8765
TAU = 0.05                    # perceptual threshold (s)
ALPHA = 60.0                  # logistic slope
BETA = 1.5                    # jitter weight

async def measure_rtt(host, port, timeout=0.1):
    start = time.perf_counter()
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout)
        writer.close()
        await writer.wait_closed()
        return max(0.0, time.perf_counter() - start)
    except Exception:
        return float('inf')

def visibility(delta_t, sigma):
    # delta_t and sigma in seconds
    z = ALPHA * (delta_t + BETA * sigma - TAU)
    return 1.0 / (1.0 + math.exp(-z))

async def stats_collector(frame_time_queue, rtt_window=10):
    rtts = []
    sigmas = []
    async for frame_time in frame_time_queue:
        rtts.append(frame_time['rtt'])
        sigmas.append(frame_time['jitter'])
        if len(rtts) > rtt_window:
            rtts.pop(0); sigmas.pop(0)
        yield (sum(rtts)/len(rtts), sum(sigmas)/len(sigmas))

async def ws_handler(websocket, path, frame_time_queue):
    # send visibility updates to connected renderer
    async for avg_rtt, avg_sigma in stats_collector(frame_time_queue):
        V = visibility(avg_rtt, avg_sigma)
        msg = {"visibility": V, "rtt": avg_rtt, "sigma": avg_sigma}
        await websocket.send(json.dumps(msg))
        await asyncio.sleep(0.05)  # 20 Hz update

async def rtt_poller(frame_time_queue):
    # poll RTT and jitter, and push into queue for aggregator
    prev = None
    while True:
        rtt = await measure_rtt(EDGE_HOST, EDGE_PORT)
        if rtt == float('inf'):
            jitter = 0.2
        else:
            jitter = abs(rtt - (prev or rtt))
        await frame_time_queue.put({'rtt': rtt, 'jitter': jitter})
        prev = rtt
        await asyncio.sleep(0.02)  # 50 Hz sampling

async def main():
    frame_time_queue = asyncio.Queue()
    start_server = websockets.serve(
        lambda ws, p: ws_handler(ws, p, frame_time_queue), "0.0.0.0", WS_PORT)
    await asyncio.gather(start_server, rtt_poller(frame_time_queue))

if __name__ == "__main__":
    asyncio.run(main())