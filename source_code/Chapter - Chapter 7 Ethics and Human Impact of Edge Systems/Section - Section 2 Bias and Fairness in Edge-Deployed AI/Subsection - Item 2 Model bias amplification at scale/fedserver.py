import flwr as fl
import numpy as np
from typing import Dict, List, Tuple

MAX_WEIGHT = 0.2  # avoid single-client domination

# compute safe normalized weights from client sample counts
def normalize_weights(sample_counts: List[int]) -> List[float]:
    total = sum(sample_counts)
    raw = [c / total for c in sample_counts]
    capped = [min(w, MAX_WEIGHT) for w in raw]
    rem = 1.0 - sum(capped)
    if rem > 0:
        # redistribute remaining mass proportionally among non-capped
        noncapped = [i for i,w in enumerate(raw) if w < MAX_WEIGHT]
        if noncapped:
            s = sum(raw[i] for i in noncapped)
            for i in noncapped:
                capped[i] += rem * (raw[i] / s)
    # ensure numerical normalization
    s = sum(capped)
    return [w / s for w in capped]

class BiasAwareWeightedAggregation(fl.server.strategy.FedAvg):
    def aggregate_fit(
        self, rnd, results, failures
    ) -> Tuple[bytes, Dict]:
        # extract parameters, sample counts, and reported bias metrics
        params_and_counts = []
        bias_reports = {}
        for client_res in results:
            params, metrics = client_res.parameters, client_res.metrics
            n = int(metrics.get("num_samples", 0))
            b = float(metrics.get("local_bias_A", 0.0))  # client A metric
            params_and_counts.append((params, n))
            bias_reports[client_res.client.cid] = b

        sample_counts = [n for (_, n) in params_and_counts]
        weights = normalize_weights(sample_counts)

        # perform weighted aggregation on model parameters (FLWR helper)
        aggregated = fl.common.parameters_to_weights(params_and_counts[0][0])
        # convert to numpy arrays and aggregate
        weight_list = [fl.common.parameters_to_weights(p) for (p, _) in params_and_counts]
        agg = [sum(w * arr for w, arr in zip(weights, col)) 
               for col in zip(*weight_list)]
        aggregated_parameters = fl.common.weights_to_parameters(agg)

        # compute global amplification metric for logging
        global_A = sum(w * float(bias_reports[cid]) 
                       for cid, w in zip(bias_reports.keys(), weights))
        metrics = {"global_bias_A": global_A}
        return aggregated_parameters, metrics

# start server with this strategy
strategy = BiasAwareWeightedAggregation()
fl.server.start_server(server_address="0.0.0.0:8080", strategy=strategy)