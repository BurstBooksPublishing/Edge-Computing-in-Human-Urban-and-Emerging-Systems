#!/usr/bin/env python3
# Production-ready resource allocator for edge gateway.
import logging, time, json, requests
import psutil
import cvxpy as cp

logging.basicConfig(level=logging.INFO)
TELEMETRY_URL = "http://localhost:9000/telemetry"  # push metrics

def fetch_task_metrics():
    # Query local agent for task profiles (returns dict of tasks with
    # 'min_cpu','max_cpu','impact_latency','impact_energy').
    r = requests.get("http://localhost:9100/tasks")
    r.raise_for_status()
    return r.json()

def allocate(cpu_total, tasks):
    n = len(tasks)
    x = cp.Variable(n)  # CPU fraction per task
    lat = cp.sum([tasks[i]['impact_latency'] / x[i] for i in range(n)])  # approx
    energy = cp.sum([tasks[i]['impact_energy'] * x[i] for i in range(n)])
    obj = cp.Minimize(0.6*lat + 0.4*energy)
    constraints = [x >= [t['min_cpu'] for t in tasks],
                   x <= [t['max_cpu'] for t in tasks],
                   cp.sum(x) <= cpu_total]
    prob = cp.Problem(obj, constraints)
    prob.solve(solver=cp.OSQP, warm_start=True)
    if prob.status not in ("optimal","optimal_inaccurate"):
        raise RuntimeError("Allocation failed: %s" % prob.status)
    return {tasks[i]['name']: float(x.value[i]) for i in range(n)}

def push_alloc(res):
    # Apply via container or cgroup API; here we POST to local controller.
    requests.post("http://localhost:9100/apply", json=res, timeout=2).raise_for_status()

def main_loop():
    while True:
        try:
            tasks = fetch_task_metrics()
            cpu_total = psutil.cpu_count(logical=False)  # physical cores
            alloc = allocate(cpu_total, tasks)
            push_alloc(alloc)
            requests.post(TELEMETRY_URL, json={"alloc":alloc})
        except Exception as e:
            logging.exception("Allocation cycle failed")
        time.sleep(1.0)

if __name__ == "__main__":
    main_loop()