#!/usr/bin/env python3
"""Compute fragility and recommend mitigations for edge nodes."""
from typing import Dict, List, Tuple
import numpy as np
import logging

logger = logging.getLogger("fragility")
logging.basicConfig(level=logging.INFO)

# Example weights for categories: sensing, compute, network, control
DEFAULT_WEIGHTS = {"sensing":0.35, "compute":0.25, "network":0.25, "control":0.15}

def compute_fragility(metrics: Dict[str,float], weights: Dict[str,float]=DEFAULT_WEIGHTS) -> float:
    """
    metrics: normalized values in [0,1] for keys matching weights.
    returns fragility F in [0,1].
    """
    keys = list(weights.keys())
    vals = np.array([metrics.get(k, 0.0) for k in keys], dtype=float)
    w = np.array([weights[k] for k in keys], dtype=float)
    if not np.isclose(w.sum(), 1.0):
        w = w / w.sum()
    F = float(np.dot(w, vals))
    return max(0.0, min(1.0, F))

def social_visibility(F: float, T: float, kappa: float = 10.0) -> float:
    """Logistic visibility model; T in [0,1], higher T means more tolerant."""
    x = kappa * (F - T)
    return 1.0 / (1.0 + np.exp(-x))

def recommend_actions(F: float, T: float) -> List[str]:
    """Return prioritized actions for an orchestrator or operator."""
    pvis = social_visibility(F, T)
    actions = []
    if F > 0.8 or pvis > 0.9:
        actions.append("failover: route to redundant node")
        actions.append("rollback: disable non-critical features")
        actions.append("notify: escalate to human operator")
    elif F > 0.5 or pvis > 0.5:
        actions.append("scale-up: schedule local container replicas")
        actions.append("degrade-gracefully: lower sensor sampling / model resolution")
    else:
        actions.append("monitor: increase telemetry frequency")
    return actions

# Example usage with telemetry from node
if __name__ == "__main__":
    telemetry = {"sensing":0.6, "compute":0.3, "network":0.4, "control":0.2}
    T = 0.4  # low tolerance (safety-critical)
    F = compute_fragility(telemetry)
    logger.info("Fragility F=%.3f, visibility=%.3f", F, social_visibility(F,T))
    for a in recommend_actions(F,T):
        logger.info("Action: %s", a)