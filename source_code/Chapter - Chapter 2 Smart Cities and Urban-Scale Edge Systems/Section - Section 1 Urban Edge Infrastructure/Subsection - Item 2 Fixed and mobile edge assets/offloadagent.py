#!/usr/bin/env python3
# Minimal production-ready offload agent. Requires psutil, paho-mqtt, requests.
import time, json, psutil, requests
import paho.mqtt.client as mqtt

MQTT_BROKER = "mqtt.city.example"
REPORT_TOPIC = "edge/metrics"
DECISION_TOPIC = "edge/decision"
CHECK_INTERVAL = 2.0  # seconds

def collect_metrics():
    # CPU, memory, battery (if available), and simple network quality probe
    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory().percent
    try:
        # simple HTTP RTT probe to local MEC endpoint list
        endpoints = ["http://mec1.local/ping", "http://mec2.local/ping"]
        rtts = [requests.get(ep, timeout=0.5).elapsed.total_seconds() for ep in endpoints]
        best_rtt = min(rtts)
    except Exception:
        best_rtt = 1.0  # conservative fallback
    metrics = {"cpu": cpu, "mem": mem, "rtt": best_rtt, "ts": time.time()}
    return metrics

def decide(metrics, policy):
    # Simple policy: prefer MEC if RTT < threshold and CPU available.
    if metrics["rtt"] < policy["rtt_thresh"] and metrics["cpu"] < policy["cpu_thresh"]:
        return {"target": "mec", "reason": "low_rtt_and_cpu_ok"}
    if metrics["cpu"] >= policy["cpu_offload_cpu"]:
        return {"target": "offload", "reason": "local_overloaded"}
    return {"target": "local", "reason": "default"}

def main():
    client = mqtt.Client()
    client.connect(MQTT_BROKER)
    policy = {"rtt_thresh": 0.050, "cpu_thresh": 70.0, "cpu_offload_cpu": 85.0}
    while True:
        m = collect_metrics()
        client.publish(REPORT_TOPIC, json.dumps(m))
        decision = decide(m, policy)
        client.publish(DECISION_TOPIC, json.dumps({"decision": decision, "metrics": m}))
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()