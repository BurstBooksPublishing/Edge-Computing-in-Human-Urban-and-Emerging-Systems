#!/usr/bin/env python3
"""Recommend deployment option given timing and energy budgets."""
from typing import List, Tuple

# per-layer metrics (latency_ms, power_mW)
layers: List[Tuple[float, float]] = [
    ("container_runtime", 5.0, 150.0),
    ("sidecar_logging", 2.5, 30.0),
    ("policy_agent", 3.0, 20.0),
    ("telemetry", 1.5, 10.0),
]

L0_ms = 10.0                      # base processing latency (ms)
budget_ms = 50.0                  # latency budget (ms)
P0_mW = 1000.0                    # baseline power draw (mW)
event_rate = 20.0                 # events per second

def recommend(layers, L0_ms, budget_ms, P0_mW, event_rate):
    cum_lat = 0.0
    cum_power = 0.0
    included = []
    for name, tau, p in layers:
        if L0_ms + cum_lat + tau > budget_ms:
            break
        cum_lat += tau
        cum_power += p
        included.append(name)
    energy_per_event = (P0_mW + cum_power) / event_rate  # mJ/s per event proxy
    # simple scoring: fewer layers preferred if latency tight
    if L0_ms + cum_lat <= 0.5 * budget_ms:
        tier = "containerized_edge"   # safe to platformize
    elif L0_ms + cum_lat <= budget_ms:
        tier = "hybrid_federated"     # limited platformization
    else:
        tier = "bare_metal/RTOS"      # avoid platformization
    return {
        "included_layers": included,
        "total_added_latency_ms": cum_lat,
        "total_added_power_mW": cum_power,
        "energy_per_event_mW_per_event": energy_per_event,
        "recommended_tier": tier,
    }

if __name__ == "__main__":
    result = recommend(layers, L0_ms, budget_ms, P0_mW, event_rate)
    print(result)  # integrate with CI to gate platform rollouts