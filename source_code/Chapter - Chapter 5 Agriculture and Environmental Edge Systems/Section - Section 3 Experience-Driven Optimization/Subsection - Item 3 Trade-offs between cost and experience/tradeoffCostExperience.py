import numpy as np

# input arrays: q_gain[b] = QoE gain for bitrate b; cost[b] = cost per segment at bitrate b
# bandwidth_budget: bytes/s available for this session; seg_dur: seconds per segment
def select_bitrates(q_gain, cost, bandwidth_budget, seg_dur):
    # compute ratio and sort descending
    ratio = q_gain / (cost + 1e-9)
    order = np.argsort(-ratio)
    chosen = np.zeros_like(q_gain, dtype=bool)
    used_band = 0.0
    # assume bitrate index maps to bytes per seg in cost array if available
    bytes_per_seg = cost * seg_dur  # cost may include proportional data cost
    for idx in order:
        if used_band + bytes_per_seg[idx] <= bandwidth_budget:
            chosen[idx] = True
            used_band += bytes_per_seg[idx]
    return chosen

# Example usage: q_gain for [1,2,3] bitrates, cost proportional to bytes
# chosen indicates which bitrates to use for upcoming segments