import numpy as np

def minimal_local_fraction(net_samples, edge_samples, local_samples,
                           sched_samples, D, alpha, resolution=101):
    """
    Compute minimal x in [0,1] s.t. Pr(L_total > D) <= alpha.
    net_samples, edge_samples, local_samples, sched_samples: 1D numpy arrays of ms.
    D: deadline in ms; alpha: allowed tail probability.
    resolution: discretization of x (default 101 points).
    """
    # Precompute sample stacks (bootstrap alignment via random permutation)
    N = min(map(len, (net_samples, edge_samples, local_samples, sched_samples)))
    if N < 100:
        raise ValueError("Need >=100 samples for stable tail estimates")
    # Randomly sample without replacement for Monte Carlo mixing
    idx = np.random.choice(len(net_samples), size=N, replace=False)
    net = net_samples[idx]
    edge = edge_samples[idx % len(edge_samples)]  # tolerate different lengths
    local = local_samples[idx % len(local_samples)]
    sched = sched_samples[idx % len(sched_samples)]
    xs = np.linspace(0.0, 1.0, resolution)
    for x in xs:
        total = sched + x * local + (1.0 - x) * (net + edge)
        tail = np.mean(total > D)
        if tail <= alpha:
            return float(x)  # smallest feasible x due to increasing xs
    return 1.0  # must run everything locally to meet deadline

# Example usage (to be called from an orchestrator)
# net_samples = np.load("net_samples.npy")
# edge_samples = np.load("edge_samples.npy")
# local_samples = np.load("local_samples.npy")
# sched_samples = np.load("sched_samples.npy")
# x = minimal_local_fraction(net_samples, edge_samples, local_samples, sched_samples, D=50, alpha=0.01)