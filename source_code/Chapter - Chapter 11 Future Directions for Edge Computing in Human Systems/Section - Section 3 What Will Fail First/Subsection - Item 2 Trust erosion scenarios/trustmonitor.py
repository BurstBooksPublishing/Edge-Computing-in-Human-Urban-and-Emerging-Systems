#!/usr/bin/env python3
# Minimal production-ready trust monitor for edge controllers.
import json, time, hmac, hashlib, logging
import paho.mqtt.client as mqtt

# Configuration (use env vars or secure config store in production)
BROKER = "mqtt.city-broker.local"
PORT = 8883
CLIENT_ID = "edge-trust-mon-01"
TLS_CONFIG = ("/etc/ssl/ca.pem", None, None)  # CA path
HMAC_KEY = b"replace_with_secure_key"

logging.basicConfig(level=logging.INFO)
trust = 1.0  # initial trust

def sign_payload(payload: bytes) -> str:
    return hmac.new(HMAC_KEY, payload, hashlib.sha256).hexdigest()

def compute_delta(event: dict) -> float:
    # event: {'visibility':0.0-1.0,'severity':0.0-1.0,'timestamp':...}
    lambda_v = 1.5
    return lambda_v * event.get('visibility',0.5) * event.get('severity',0.5)

def apply_event(event: dict):
    global trust
    delta = compute_delta(event)
    tau = time.time() - event.get('timestamp', time.time())
    # remediation factor decays with detection latency
    rem_factor = max(0.0, 1.0 - 0.1 * min(tau, 100))
    trust = max(0.0, trust - delta * (1.0 - rem_factor))
    logging.info("Applied event: delta=%.3f tau=%.1fs trust=%.3f", delta, tau, trust)

def publish_trust(client: mqtt.Client):
    payload = json.dumps({"trust": trust, "ts": time.time()}).encode()
    sig = sign_payload(payload)
    client.publish("city/edge/trust", payload + b"\n" + sig.encode(), qos=1)

def main():
    client = mqtt.Client(CLIENT_ID)
    client.tls_set(ca_certs=TLS_CONFIG[0])
    client.connect(BROKER, PORT)
    client.loop_start()
    # Replace with real event stream (local queue, webhook, or kafka)
    sample_events = [
        {'visibility':0.8,'severity':0.9,'timestamp':time.time()-5},
        {'visibility':0.6,'severity':0.3,'timestamp':time.time()-60}
    ]
    for ev in sample_events:
        apply_event(ev)
        publish_trust(client)
        time.sleep(1)
    client.loop_stop()
    client.disconnect()

if __name__ == "__main__":
    main()