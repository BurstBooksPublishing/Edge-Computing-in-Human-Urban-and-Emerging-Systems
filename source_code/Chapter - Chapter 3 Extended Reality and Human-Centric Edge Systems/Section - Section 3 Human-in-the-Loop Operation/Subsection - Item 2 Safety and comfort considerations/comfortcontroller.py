#!/usr/bin/env python3
# Production-ready asyncio controller for comfort-driven fidelity scaling.

import asyncio
import math
import logging
import requests

XR_METRICS_URL = "http://127.0.0.1:8080/metrics"   # JSON: rtt_ms, frame_ms, rtt_var_ms, skin_temp_c
XR_CONTROL_URL = "http://127.0.0.1:8080/control"   # POST JSON: {"render_fidelity": float}
CHECK_INTERVAL = 0.5  # seconds
COMFORT_THRESH = 0.7  # normalized threshold

logging.basicConfig(level=logging.INFO)

def comfort_cost(metrics):
    # sigmoid on total latency + jitter + thermal excess
    total_ms = metrics["rtt_ms"] + metrics["frame_ms"]
    sigmoid = lambda x, k=0.1: 1.0 / (1.0 + math.exp(-k*(x-35.0)))  # 35ms knee
    latency_term = sigmoid(total_ms)
    jitter_term = min(1.0, metrics.get("rtt_var_ms", 0.0) / 20.0)
    thermal_term = max(0.0, (metrics.get("skin_temp_c", 36.5) - 36.5) / 5.0)
    # weights tuned for industrial AR; adjust per deployment
    return 0.6*latency_term + 0.3*jitter_term + 0.1*thermal_term

async def poll_and_control():
    current_fidelity = 1.0
    session = requests.Session()
    while True:
        try:
            r = session.get(XR_METRICS_URL, timeout=0.2)
            r.raise_for_status()
            metrics = r.json()
            cost = comfort_cost(metrics)
            logging.info("metrics=%s cost=%.3f fidelity=%.2f", metrics, cost, current_fidelity)
            if cost > COMFORT_THRESH and current_fidelity > 0.3:
                current_fidelity = max(0.3, current_fidelity - 0.1)
                session.post(XR_CONTROL_URL, json={"render_fidelity": current_fidelity}, timeout=0.2)
            elif cost < (COMFORT_THRESH - 0.2) and current_fidelity < 1.0:
                current_fidelity = min(1.0, current_fidelity + 0.1)
                session.post(XR_CONTROL_URL, json={"render_fidelity": current_fidelity}, timeout=0.2)
        except Exception as e:
            logging.warning("poll/control error: %s", e)
        await asyncio.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    asyncio.run(poll_and_control())