#!/usr/bin/env python3
# Production-ready: pip install numpy scipy
import numpy as np
from scipy.stats import norm

# Component stats: (mean_ms, std_ms)
components = {
    'sensor': (1.0, 0.2),
    'proc':   (2.0, 0.5),
    'render': (6.0, 1.0),
    'network':(13.0, 3.0),
    'display':(5.6, 0.8)
}

def compute_tail(components, target_ms):
    mus = np.array([v[0] for v in components.values()])
    sigs = np.array([v[1] for v in components.values()])
    mu_total = mus.sum()
    sigma_total = np.sqrt((sigs**2).sum())
    p_miss = 1.0 - norm.cdf((target_ms - mu_total) / sigma_total)
    return mu_total, sigma_total, p_miss

if __name__ == '__main__':
    target = 20.0  # ms comfort target
    mu, sigma, p_miss = compute_tail(components, target)
    print(f"Expected MTP: {mu:.2f} ms ± {sigma:.2f} ms (1σ)")
    print(f"P(MTP > {target} ms) ≈ {p_miss:.6f}")
    # engineers iterate by modifying 'components' and re-running