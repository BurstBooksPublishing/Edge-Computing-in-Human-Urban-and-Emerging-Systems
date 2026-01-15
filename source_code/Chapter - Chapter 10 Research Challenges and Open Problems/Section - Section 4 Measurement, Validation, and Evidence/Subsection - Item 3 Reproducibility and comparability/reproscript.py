#!/usr/bin/env python3
"""
Collect system provenance, run a containerized experiment deterministically,
and compute a simple reproducibility score between two runs.
"""
import json, subprocess, hashlib, time, os, sys, tempfile, shlex
from pathlib import Path
import statistics, math

OUTDIR = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("experiment_out")
OUTDIR.mkdir(parents=True, exist_ok=True)

def run_cmd(cmd):
    return subprocess.check_output(shlex.split(cmd)).decode().strip()

def sha256_of_file(path):
    h = hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()

# Capture provenance
manifest = {}
manifest['timestamp'] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
manifest['uname'] = run_cmd("uname -a")
manifest['cpuinfo'] = run_cmd("cat /proc/cpuinfo | head -n 50")
manifest['dmesg'] = run_cmd("dmesg | tail -n 200")
# container image digest (example)
IMAGE = "myregistry.local/edge-pedcount:latest"
manifest['image'] = IMAGE
try:
    manifest['image_digest'] = run_cmd(f"docker inspect --format='{{{{index .RepoDigests 0}}}}' {IMAGE}")
except Exception:
    manifest['image_digest'] = None

# Save manifest
manifest_path = OUTDIR / "provenance.json"
with open(manifest_path, "w") as f:
    json.dump(manifest, f, indent=2)

# Deterministic container run wrapper (bind mounts, CPU pinning, fixed seed)
def run_experiment(run_id, seed=42, timeout=60):
    run_dir = OUTDIR / f"run_{run_id}"
    run_dir.mkdir(exist_ok=True)
    log = run_dir / "experiment.log"
    env = f"EXPERIMENT_SEED={seed}"
    cmd = (
        f"docker run --rm --env {env} --cpuset-cpus=0 "
        f"-v {run_dir}:/work -w /work {IMAGE} ./run_inference.sh {seed}"
    )
    with open(log, "wb") as out:
        proc = subprocess.Popen(shlex.split(cmd), stdout=out, stderr=subprocess.STDOUT)
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            out.write(b"\n# TIMEOUT\n")
    # return path to output metrics (assumes container writes metrics.json)
    return run_dir / "metrics.json"

# Execute two runs
m1 = run_experiment(1, seed=1234)
m2 = run_experiment(2, seed=1234)

def load_metrics(p):
    if not p.exists():
        return {}
    return json.load(open(p))

metrics1 = load_metrics(m1)
metrics2 = load_metrics(m2)

# Basic reproducibility scoring: compare primary metric distributions
def reproducibility_score(a_vals, b_vals, beta=1.0):
    mu_sig = (statistics.mean(a_vals)+statistics.mean(b_vals))/2.0
    sigma_noise = statistics.pstdev(a_vals + b_vals)
    # fake D_cfg: 0 if image_digest equal else 1
    D_cfg = 0.0 if manifest.get('image_digest') else 1.0
    return math.exp(-beta*D_cfg) * (mu_sig/(mu_sig+sigma_noise+1e-9))

# Example assumes metrics contain 'fps' samples
a = metrics1.get('fps_samples', [])
b = metrics2.get('fps_samples', [])
score = reproducibility_score(a,b)
with open(OUTDIR / "repro_score.json",'w') as f:
    json.dump({'score': score, 'manifest': manifest}, f, indent=2)
print("Reproducibility score:", score)