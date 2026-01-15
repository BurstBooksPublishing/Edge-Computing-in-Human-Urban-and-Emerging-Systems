#!/usr/bin/env python3
# Production-ready: numpy only, no external services.
import math
from math import comb

def quorum_availability(k: int, n: int, r: float) -> float:
    # r is single-node reliability (0..1)
    return sum(comb(n, i) * (r**i) * ((1 - r)**(n - i)) for i in range(k, n + 1))

def minimal_n_for_target(k: int, r: float, target: float, n_max: int = 20) -> int:
    for n in range(k, n_max + 1):
        if quorum_availability(k, n, r) >= target:
            return n
    raise ValueError("Target availability not achievable within n_max")

# Example: node reliability 0.98, quorum 3, target availability 0.999
if __name__ == "__main__":
    node_r = 0.98
    k = 3
    target = 0.999
    n = minimal_n_for_target(k, node_r, target)
    print(f"Minimal n for k={k}, r={node_r:.2f}, target={target}: n={n}")
    print(f"Availability: {quorum_availability(k,n,node_r):.6f}")