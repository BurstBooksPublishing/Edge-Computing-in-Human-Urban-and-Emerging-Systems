import numpy as np
from scipy.optimize import minimize_scalar

# Model parameters (example values; replace with measured values)
R = 1e10             # ops/s per km^2
c = 1e9              # ops/s per node
P_idle = 5.0         # W per node
P_peak = 50.0        # W per node
beta = 1e-9          # J per op-hop
k = 10.0             # hop constant for h(d)=k/sqrt(d)
E_emb = 5e5          # kJ -> J (500 kJ)
T = 5*365*24*3600    # lifetime seconds

# Convert embodied energy to Watts (amortized)
E_emb_W = E_emb / T

def h_of_d(d):
    return k / np.sqrt(d)

def power_area(d):
    u = min(1.0, R/(d*c))                  # utilization
    P_node = P_idle + (P_peak-P_idle)*u
    return d*P_node + beta*R*h_of_d(d)

def total_env_cost(d, gamma=0.4):
    # gamma: kgCO2eq per kWh equivalent (example)
    P_A = power_area(d)                    # W per km^2
    # Operating emissions (kgCO2/s -> kgCO2 per second)
    op_em = P_A * gamma / 3600.0           # kgCO2 per second (kWh factor absorbed in gamma)
    emb_em = d * E_emb_W * gamma / 3600.0  # amortized embodied kgCO2 per second
    return op_em + emb_em

# Minimize cost over realistic density bounds
res = minimize_scalar(lambda x: total_env_cost(x),
                      bounds=(1.0, 1e4), method='bounded')
optimal_d = res.x
optimal_cost = res.fun

# Output for deployment planning
print(f"Optimal density: {optimal_d:.1f} nodes/km^2")
print(f"Estimated emissions (/s): {optimal_cost:.3e} kgCO2/s")