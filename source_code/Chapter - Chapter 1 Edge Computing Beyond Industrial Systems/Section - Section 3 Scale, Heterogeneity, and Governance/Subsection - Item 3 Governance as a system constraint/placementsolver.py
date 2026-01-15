#!/usr/bin/env python3
"""
Placement solver: minimize latency under capacity and residency constraints.
Integrate with control plane (K3s/KubeEdge) as part of scheduler extension.
"""
import pulp
from typing import Dict, List, Set, Tuple

# Inputs (populate from inventory / policy DB)
workloads: List[str] = ["cam_1_analytics", "cam_2_analytics", "agg_service"]
nodes: List[str] = ["mec_node_a", "mec_node_b", "cloud_region_x"]
latency: Dict[Tuple[str,str], float] = {("cam_1_analytics","mec_node_a"):5.0,
                                        ("cam_1_analytics","mec_node_b"):8.0,
                                        ("cam_1_analytics","cloud_region_x"):50.0,
                                        # ... other entries ...
                                       }
resource_req: Dict[str,float] = {"cam_1_analytics":2.0, "cam_2_analytics":2.0, "agg_service":1.0}
capacity: Dict[str,float] = {"mec_node_a":4.0, "mec_node_b":2.0, "cloud_region_x":100.0}
# Residency: allowed nodes per workload (policy DB, e.g., city-owned MEC only for raw video)
allowed_nodes: Dict[str, Set[str]] = {
    "cam_1_analytics": {"mec_node_a","mec_node_b"},
    "cam_2_analytics": {"mec_node_a"},
    "agg_service": {"mec_node_a","mec_node_b","cloud_region_x"},
}

# Build ILP
prob = pulp.LpProblem("edge_placement", pulp.LpMinimize)
x = pulp.LpVariable.dicts("x", (workloads, nodes), lowBound=0, upBound=1, cat="Binary")

# Objective: minimize total latency
prob += pulp.lpSum(latency[(i,j)] * x[i][j] for i in workloads for j in nodes if (i,j) in latency)

# Each workload placed exactly once (or adjust for replication policies)
for i in workloads:
    prob += pulp.lpSum(x[i][j] for j in nodes) == 1

# Capacity constraints
for j in nodes:
    prob += pulp.lpSum(resource_req[i] * x[i][j] for i in workloads) <= capacity[j]

# Residency / governance constraints: disallow placements not in allowed_nodes
for i in workloads:
    for j in nodes:
        if j not in allowed_nodes[i]:
            prob += x[i][j] == 0

# Solve and output decisions
prob.solve(pulp.PULP_CBC_CMD(msg=False))
placement = {i: next(j for j in nodes if pulp.value(x[i][j]) > 0.5) for i in workloads}
print("Placement decisions:", placement)
# Integrate: annotate Kubernetes PodSpec with nodeSelector and admission validation using OPA