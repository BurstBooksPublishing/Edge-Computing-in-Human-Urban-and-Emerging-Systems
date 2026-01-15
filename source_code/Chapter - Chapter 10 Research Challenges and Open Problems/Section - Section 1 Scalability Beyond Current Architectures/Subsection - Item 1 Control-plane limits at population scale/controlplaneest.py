#!/usr/bin/env python3
"""Estimate control-plane worker count using Erlang C queueing.
Suitable for CI checks of edge controller sizing (K3s/KubeEdge)."""
import math

def erlang_c(lambda_r, mu, c):
    rho = lambda_r / (c * mu)
    if rho >= 1.0:
        return 1.0  # system unstable
    a = lambda_r / mu
    # sum_{n=0}^{c-1} a^n / n!
    sum_term = sum((a**n) / math.factorial(n) for n in range(c))
    last = (a**c) / math.factorial(c)
    numerator = last * (c * mu) / (c * mu - lambda_r)
    return numerator / (sum_term + numerator)

def required_cores(N, h, e, proc_time_s, target_util=0.7):
    lam = N * (h + e)
    mu = 1.0 / proc_time_s
    # minimal cores to keep utilization < target
    c = max(1, math.ceil(lam / (target_util * mu)))
    # refine to ensure reasonable wait probability
    for extra in range(0, 50):
        wc = erlang_c(lam, mu, c + extra)
        if wc < 0.05:  # <5% wait prob
            return c + extra, lam, mu, wc
    return c + 50, lam, mu, erlang_c(lam, mu, c + 50)

if __name__ == "__main__":
    # realistic scenario: city-scale endpoints
    N = 1_000_000
    h = 1.0 / 60.0      # heartbeat per second
    e = 1.0 / 3600.0    # event per second
    proc_time_s = 0.002 # avg processing time per message
    cores, lam, mu, p_wait = required_cores(N, h, e, proc_time_s)
    bw_per_msg_bytes = 512
    bw_Mbps = (lam * bw_per_msg_bytes * 8) / 1e6
    print(f"Estimated cores: {cores}")
    print(f"Arrival rate: {lam:.1f} msg/s, svc rate/core: {mu:.1f} msg/s")
    print(f"Probability of wait: {p_wait:.3f}, net BW: {bw_Mbps:.1f} Mbps")