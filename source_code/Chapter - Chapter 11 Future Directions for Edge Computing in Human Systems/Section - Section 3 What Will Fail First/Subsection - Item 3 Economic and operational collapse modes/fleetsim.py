#!/usr/bin/env python3
"""Simulate fleet economics and failure propagation for edge deployments."""
from typing import Tuple
import numpy as np
import logging

logging.basicConfig(level=logging.INFO)

def economic_tipping(N: int, r: float, c_o: float, C_infra: float) -> bool:
    """Return True if fleet is economically unsustainable."""
    return (N * r) < (N * c_o + C_infra)

def simulate_epidemic(T: int, dt: float, beta: float, gamma: float,
                      f0: float) -> np.ndarray:
    """Discrete-time integration of df/dt = beta f (1-f) - gamma f."""
    steps = int(T / dt)
    f = np.empty(steps + 1)
    f[0] = np.clip(f0, 0.0, 1.0)
    for i in range(steps):
        df = beta * f[i] * (1.0 - f[i]) - gamma * f[i]
        f[i+1] = np.clip(f[i] + df * dt, 0.0, 1.0)
    return f

if __name__ == "__main__":
    # Example parameters for an urban fleet
    N = 3000
    r = 0.8      # revenue per node per unit time
    c_o = 0.7    # operating cost per node
    C_infra = 500.0  # shared infra cost
    unsustainable = economic_tipping(N, r, c_o, C_infra)
    logging.info("Economic unsustainable: %s", unsustainable)

    # Epidemic simulation: parameters tuned from operational logs
    T = 72.0     # hours
    dt = 0.1
    beta = 0.25  # contagion rate from rollout or network dependency
    gamma = 0.10 # repair rate per hour
    f = simulate_epidemic(T, dt, beta, gamma, f0=0.01)
    # f contains the time series of failed-fraction for visualization
    logging.info("Max failed fraction: %.3f", float(f.max()))