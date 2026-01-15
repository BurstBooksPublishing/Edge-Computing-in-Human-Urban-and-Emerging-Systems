from typing import NamedTuple

class Params(NamedTuple):
    E_local: float          # J per task for local inference
    E_tx: float             # J per task for transmission
    E_remote: float         # J per task for remote processing
    L_local: float          # s per task local latency (incl queue)
    L_tx: float             # s per task transmission RTT
    L_remote: float        # s per task remote processing
    mu_local: float         # local service rate (tasks/s)
    lambda_total: float    # incoming task rate (tasks/s)
    L_sla: float           # latency SLA (s)

def placement_decision(p: Params):
    """Return boolean choose_local and max_local_fraction f_max that meets capacity/SLA."""
    choose_local = (p.E_local < (p.E_tx + p.E_remote)) and (p.L_local <= p.L_sla)
    # capacity constraint: f * lambda_total < mu_local  => f_max_capacity
    f_max_capacity = max(0.0, min(1.0, (p.mu_local - 1e-12) / p.lambda_total))  # avoid div by zero
    # SLA constraint: f*L_local + (1-f)*(L_tx+L_remote) <= L_sla  => solve for f
    denom = p.L_local - (p.L_tx + p.L_remote)
    if abs(denom) < 1e-12:
        f_max_sla = 1.0 if p.L_local <= p.L_sla else 0.0
    else:
        f_req = (p.L_sla - (p.L_tx + p.L_remote)) / denom
        f_max_sla = max(0.0, min(1.0, f_req))
    # effective feasible fraction
    f_feasible = min(f_max_capacity, f_max_sla)
    return choose_local, f_feasible

# Example usage (values must come from instrumentation or energy models)
# params = Params(E_local=0.5, E_tx=0.1, E_remote=0.2, L_local=0.05,
#                 L_tx=0.1, L_remote=0.05, mu_local=10.0, lambda_total=5.0, L_sla=0.2)
# decision, f = placement_decision(params)