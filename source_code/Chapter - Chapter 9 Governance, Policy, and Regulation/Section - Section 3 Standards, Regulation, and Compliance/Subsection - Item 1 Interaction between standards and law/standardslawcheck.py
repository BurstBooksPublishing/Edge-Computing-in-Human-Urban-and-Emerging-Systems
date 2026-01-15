#!/usr/bin/env python3
# Checks device manifest against standard and legal policies, emits report and evidence checklist.
import json, sys, logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
def load_json(p): return json.loads(Path(p).read_text())

def map_requirements(manifest, policies):
    # policies: dict{name: {"requirements": {req_id: {"type":"standard"|"law","desc":...}}}}
    coverage = {}
    for name, pol in policies.items():
        for req_id, req in pol.get("requirements", {}).items():
            # decide if manifest claims control for req_id
            satisfied = manifest.get("controls", {}).get(req_id, False)
            coverage[req_id] = {"policy": name, "type": req.get("type"), "satisfied": bool(satisfied)}
    return coverage

def summarize(coverage):
    total = len(coverage)
    gaps = [r for r in coverage.values() if not r["satisfied"] and r["type"]=="law"]
    report = {"total_reqs": total, "law_gaps": len(gaps), "gaps": gaps}
    return report

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: checker.py device_manifest.json policies.json"); sys.exit(2)
    manifest = load_json(sys.argv[1])
    policies = load_json(sys.argv[2])
    cov = map_requirements(manifest, policies)
    rep = summarize(cov)
    print(json.dumps(rep, indent=2))
    # Engineers should attach cryptographic evidence (hash, signed logs) per-gap.