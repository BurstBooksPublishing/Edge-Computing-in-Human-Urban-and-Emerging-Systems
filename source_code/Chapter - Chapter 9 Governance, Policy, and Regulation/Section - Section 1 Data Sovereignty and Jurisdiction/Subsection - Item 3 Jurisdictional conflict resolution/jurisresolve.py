#!/usr/bin/env python3
# Minimal, production-ready policy resolver for edge nodes.
from dataclasses import dataclass
from typing import Dict, List, Tuple
import math, json, datetime

# Simple point-in-polygon for geofence checks (winding number)
def point_in_poly(x: float, y: float, poly: List[Tuple[float,float]]) -> bool:
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]; xj, yj = poly[j]
        intersect = ((yi > y) != (yj > y)) and \
                    (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi)
        if intersect:
            inside = not inside
        j = i
    return inside

@dataclass
class PolicyAction:
    id: str
    latency_penalty: float
    legal_risk_score: float
    cost: float

# Example policy table produced by legal team: mapping jurisdiction set to allowed actions
POLICY_TABLE = {
    "national_sensitive": ["retain_local", "encrypt_export"],
    "municipal_public": ["retain_local", "export_raw"]
}

ACTIONS: Dict[str, PolicyAction] = {
    "retain_local": PolicyAction("retain_local", 0.0, 0.0, 0.1),
    "encrypt_export": PolicyAction("encrypt_export", 0.1, 0.01, 0.5),
    "export_raw": PolicyAction("export_raw", 0.05, 0.2, 1.0),
    "drop": PolicyAction("drop", 0.0, 0.0, 0.0),
}

WEIGHTS = {"w_L":0.5, "w_R":0.4, "w_C":0.1}

def resolve_action(predicates: List[str]) -> Tuple[str, Dict]:
    # Build key and determine allowed actions
    key = "_".join(sorted(predicates))
    allowed = POLICY_TABLE.get(key, ["retain_local"])
    # Evaluate cost per Eq. (1)
    best, best_score = None, math.inf
    for aid in allowed:
        a = ACTIONS[aid]
        score = WEIGHTS["w_L"]*a.latency_penalty + WEIGHTS["w_R"]*a.legal_risk_score + WEIGHTS["w_C"]*a.cost
        if score < best_score:
            best, best_score = aid, score
    audit = {"timestamp":datetime.datetime.utcnow().isoformat(),"predicates":predicates,"chosen":best,"score":best_score}
    return best, audit

# Example runtime: evaluate a camera frame
if __name__ == "__main__":
    # input metadata from sensor stack and GNSS
    metadata = {"lat":51.5, "lon":-0.12, "data_class":"video_biometric"}
    # map to predicates (would be more sophisticated in production)
    predicates = ["national_sensitive"] if metadata["data_class"].endswith("biometric") else ["municipal_public"]
    action, log = resolve_action(predicates)
    print(json.dumps(log))