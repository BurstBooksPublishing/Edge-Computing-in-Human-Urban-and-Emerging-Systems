#!/usr/bin/env python3
# Lightweight adaptive offload controller for edge nodes.
import time, math, requests
import psutil
from collections import deque

# Tunable weights (set by operator policy)
wL, wE, wP, wR = 0.5, 0.3, 0.15, 0.05
eta = 0.1  # learning rate
smoothing = 0.8
window = deque(maxlen=10)

def measure_metrics(offload_url):
    # CPU load and available memory
    cpu = psutil.cpu_percent(interval=None) / 100.0
    mem = psutil.virtual_memory().available / (1024**2)
    # RTT to offload endpoint (simple HTTP HEAD)
    t0 = time.time()
    try:
        r = requests.head(offload_url, timeout=0.5)
        r.raise_for_status()
        rtt = (time.time() - t0) * 1000.0
        loss = 0.0
    except Exception:
        rtt = 1000.0
        loss = 1.0
    # battery approximation (0..1) or fallback to AC
    batt = psutil.sensors_battery()
    battery_level = batt.percent / 100.0 if batt else 1.0
    return {'cpu': cpu, 'mem': mem, 'rtt': rtt, 'loss': loss, 'battery': battery_level}

def local_cost(m):
    Lloc = max(20.0, 40.0 * (1 + m['cpu']))  # empirical model ms
    Eloc = 3.0 * (1 + 2*m['cpu'])  # J per inference approx
    Ploc = 0.0
    Rloc = 0.01  # low risk
    return wL*Lloc + wE*Eloc + wP*Ploc + wR*Rloc

def remote_cost(m):
    Lrem = max(10.0, m['rtt'] + 10.0)  # ms
    Erem = 1.0 + 0.1*m['rtt']/100.0
    Prem = 1.0  # privacy penalty when data leaves device
    Rrem = 0.05 + 0.5*m['loss']
    return wL*Lrem + wE*Erem + wP*Prem + wR*Rrem

def update_boundary(b, m):
    # finite-difference gradient estimate
    eps = 1e-3
    Jb = b*local_cost(m) + (1-b)*remote_cost(m)
    Jb_eps = (b+eps)*local_cost(m) + (1-(b+eps))*remote_cost(m)
    grad = (Jb_eps - Jb)/eps
    b_new = min(1.0, max(0.0, b - eta*grad))
    # respect hard constraints: force local if battery low
    if m['battery'] < 0.15:
        b_new = 1.0
    return b_new

def main():
    offload_url = "https://edge-mec.example.local/health"
    b = 1.0  # start local
    while True:
        m = measure_metrics(offload_url)
        b = smoothing*b + (1-smoothing)*update_boundary(b, m)
        # enforce pod/container resource pinning or local model selection here
        # example: toggle model shard or set environment variable for worker
        # log and sleep
        print(f"time={time.time():.0f} b={b:.3f} metrics={m}")
        time.sleep(1.0)

if __name__ == "__main__":
    main()