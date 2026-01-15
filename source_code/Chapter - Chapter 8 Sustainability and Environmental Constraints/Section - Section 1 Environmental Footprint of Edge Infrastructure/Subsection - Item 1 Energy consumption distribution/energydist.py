import pandas as pd
import numpy as np

# Load CSV with columns: node_id, node_type, power_W, active_seconds, idle_seconds
df = pd.read_csv('energy_inventory.csv')

# Compute energy per node (Wh): power (W) * time (s) / 3600
df['E_active_Wh'] = df['power_W'] * df['active_seconds'] / 3600.0
df['E_idle_Wh'] = df['power_W'] * df['idle_seconds'] / 3600.0
df['E_total_Wh'] = df['E_active_Wh'] + df['E_idle_Wh']

# Aggregate by node_type
summary = df.groupby('node_type')['E_total_Wh'].agg(['sum', 'mean', 'count']).reset_index()

# Gini coefficient function for inequality analysis
def gini(array):
    # Array must be non-negative
    arr = np.sort(np.asarray(array).astype(float))
    n = arr.size
    if n == 0:
        return 0.0
    cum = np.cumsum(arr)
    return (2.0 * np.sum((np.arange(1, n+1) * arr))) / (n * cum[-1]) - (n + 1) / n

gini_value = gini(df['E_total_Wh'].values)

# Output concise results
print(summary.to_string(index=False))
print(f"Total energy (Wh): {df['E_total_Wh'].sum():.2f}")
print(f"Gini coefficient: {gini_value:.4f}")