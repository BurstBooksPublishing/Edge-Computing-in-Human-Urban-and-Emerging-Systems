#!/usr/bin/env python3
"""
Compute responsibility shares and write an auditable JSON record.
Designed for edge nodes with secure logging (e.g., TPM-backed storage).
"""
from typing import Dict, List
import numpy as np
import json
import time
import hashlib
from pathlib import Path

def hash_id(s: str) -> str:
    return hashlib.sha256(s.encode('utf-8')).hexdigest()

def compute_responsibility(C: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Compute normalized responsibility vector per Eq.(1)."""
    agg = C.dot(w)
    total = float(agg.sum())
    if total <= 0:
        raise ValueError("Aggregate influence must be positive")
    return agg / total

def persist_audit(record: Dict, out_dir: str = "/var/log/edge_audit") -> str:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    fname = f"resp_audit_{ts}_{hash_id(json.dumps(record))[:8]}.json"
    path = Path(out_dir) / fname
    # Atomic write recommended in production (use tempfile + rename)
    path.write_text(json.dumps(record, indent=2))
    return str(path)

# Example usage
if __name__ == "__main__":
    actors: List[str] = ["city", "vendor", "model_dev", "telco", "maintenance"]
    C = np.array([
        [0.6, 0.1, 0.1, 0.1, 0.1],
        [0.2, 0.5, 0.1, 0.1, 0.1],
        [0.1, 0.1, 0.6, 0.1, 0.1],
        [0.05,0.05,0.1, 0.7, 0.1],
        [0.05,0.25,0.1, 0.0, 0.6],
    ])  # rows: actors, cols: factors
    w = np.array([0.4, 0.2, 0.3, 0.05, 0.05])  # factor weights
    r = compute_responsibility(C, w)
    record = {
        "timestamp": time.time(),
        "actors": actors,
        "responsibility": {a: float(r[i]) for i,a in enumerate(actors)},
        "provenance": {
            "model_id": hash_id("model:v1.2"),
            "data_snapshot": hash_id("sensor_batch_2025-04-01"),
            "node": "edge-node-42"
        },
        "policy_refs": ["EU_AI_Act:AnnexII", "GDPR:Art82"]
    }
    out = persist_audit(record)
    print("Audit written to", out)