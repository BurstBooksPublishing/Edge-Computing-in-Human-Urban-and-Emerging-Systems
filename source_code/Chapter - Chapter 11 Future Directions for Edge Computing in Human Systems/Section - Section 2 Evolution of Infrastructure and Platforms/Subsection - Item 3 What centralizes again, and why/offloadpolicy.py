from typing import NamedTuple
import time, math, logging
import paho.mqtt.publish as mqtt_pub
import grpc
import requests

# Simple metrics container
class Metrics(NamedTuple):
    rtt_ms: float        # measured round-trip time to central service
    battery_pct: float   # local power state
    model_age_s: float   # seconds since last global model update

# Policy parameters tuned per deployment
LATENCY_BUDGET_MS = 100.0
BATTERY_THRESHOLD = 20.0
STALE_MODEL_PENALTY = 0.001

def score_local(m: Metrics) -> float:
    # lower is better
    energy_cost = 0.5 * max(0.0, (BATTERY_THRESHOLD - m.battery_pct))
    freshness_cost = STALE_MODEL_PENALTY * m.model_age_s
    return m.rtt_ms + 100.0 * energy_cost + freshness_cost

def score_central(m: Metrics) -> float:
    # include network cost and central processing estimate
    net = m.rtt_ms + 20.0  # estimated central processing
    governance_penalty = 0.0
    return net + governance_penalty

def decide_offload(m: Metrics) -> str:
    if score_local(m) <= score_central(m) and score_local(m) <= LATENCY_BUDGET_MS:
        return "local"
    return "central"

def publish_decision(decision: str):
    mqtt_pub.single("city/node/decision", decision, hostname="broker.local")

# gRPC call to central inference service (stub generated separately)
def call_central_inference(payload: bytes):
    with grpc.insecure_channel("central.service:50051") as ch:
        stub = None  # replace with generated stub, e.g., InferenceStub(ch)
        # stub.Predict(payload)  # production call

# Example runtime loop
def main_loop():
    while True:
        # measure metrics (implementations omitted)
        m = Metrics(rtt_ms=50.0, battery_pct=60.0, model_age_s=3600.0)
        d = decide_offload(m)
        publish_decision(d)
        if d == "central":
            call_central_inference(b"payload")
        else:
            # local inference path
            pass
        time.sleep(1.0)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main_loop()