#!/usr/bin/env python3
# Production-ready health monitor: publishes health and triggers fallback.
import time, json, subprocess
import paho.mqtt.client as mqtt

BROKER = "mqtt.city.example"
TOPIC = "edge/device/health"
DEVICE_ID = "intersection-42"
WINDOW = 300              # seconds
ALPHA = 0.1               # EWMA smoothing
THRESHOLD = 1e-3          # failure rate threshold (failures per second)

client = mqtt.Client(client_id=DEVICE_ID)
client.connect(BROKER, 1883, 60)

ewma = 0.0
last = time.time()

def publish(status):
    payload = {"id": DEVICE_ID, "ts": int(time.time()), "status": status}
    client.publish(TOPIC, json.dumps(payload), qos=1)

def trigger_local_fallback():
    # Use systemd service to enable safe-controller; preserves audit trail.
    subprocess.run(["systemctl", "start", "safe-traffic-controller.service"],
                   check=True)

def record_event(success):
    global ewma, last
    now = time.time()
    dt = now - last
    last = now
    x = 0.0 if success else 1.0
    ewma = ALPHA * x + (1 - ALPHA) * ewma
    # Convert EWMA (per-event) to rate per second over WINDOW
    rate = ewma / max(1.0, WINDOW)
    return rate

def main_loop():
    publish("starting")
    while True:
        # Integrate with ML runtime for a success/failure boolean.
        # Replace the following line with an actual inference health probe.
        success = probe_inference_health()  # implement per-platform
        rate = record_event(success)
        if rate > THRESHOLD:
            publish("degraded")
            trigger_local_fallback()
        else:
            publish("ok")
        time.sleep(1)

if __name__ == "__main__":
    main_loop()