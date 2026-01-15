#!/usr/bin/env python3
# Energy-aware EDF scheduler: compute DVFS setting and schedule tasks.
import math, subprocess, os, time
# Model parameters (tuned per SoC)
k = 1e-9           # power coefficient (W / Hz^m)
m = 2.8            # exponent for power-frequency relation
f_min = 600e6      # Hz
f_max = 1.8e9      # Hz
# Task descriptors: (cycles, period, deadline, name)
tasks = [
    (1.2e9, 0.1, 0.1, "inference"),    # 1.2G cycles, 100ms
    (2e8,   0.5, 0.5, "telemetry"),    # 200M cycles, 500ms
]
def compute_global_frequency(tasks, hyperperiod):
    # per-task minimum frequency to meet deadline
    f_req = max((C/D for C,D,_,_ in [(t[0],t[2],None,None) for t in tasks]))
    # CPU time budget requirement: sum C / hyperperiod
    f_util = sum(C for C,_,_,_ in tasks) / hyperperiod
    f = max(f_min, f_req, f_util)
    return min(f, f_max)
def set_system_frequency(f_hz):
    # try cpufreq-set; fall back to sysfs if available; require root.
    try:
        subprocess.check_call(["cpufreq-set", "-r", "-f", f"{int(f_hz)}"])
    except Exception:
        path = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_setspeed"
        if os.path.exists(path):
            with open(path, "w") as fh:
                fh.write(str(int(f_hz)))
def main_loop():
    hyper = 1.0  # choose 1s hyperperiod for periodic tasks
    while True:
        f = compute_global_frequency(tasks, hyper)
        set_system_frequency(f)
        # simple EDF dispatch: run each task when deadline arrives (placeholder)
        # real system would integrate with RTOS or cgroups to dispatch work.
        print(f"Setting frequency {f/1e6:.1f}MHz to meet deadlines")
        time.sleep(1.0)
if __name__ == "__main__":
    main_loop()