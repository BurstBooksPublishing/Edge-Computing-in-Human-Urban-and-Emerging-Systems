#!/usr/bin/env python3
"""
Production-ready visibility agent for edge nodes.
Assumptions: paho-mqtt installed, secure key available via OS key store or HSM.
Replace hmac_key retrieval with TPM-based signing on supported SoCs.
"""
import json
import time
import hmac
import hashlib
import asyncio
import paho.mqtt.client as mqtt
from collections import deque

MQTT_BROKER = "mqtt.example.city:8883"     # TLS-enabled broker (MEC or cloud)
MQTT_TOPIC = "city/traffic/visibility"
BATCH_SIZE = 10
BATCH_INTERVAL = 1.0                        # seconds

# Securely obtain HMAC key from OS keystore or HSM.
def get_hmac_key():
    # Placeholder: integrate with TPM or ATECC SDK for production.
    return b"REPLACE_WITH_SECURE_KEY_FROM_HSM"

def sign_record(record: bytes, key: bytes) -> str:
    # Produce hex HMAC for compact signed provenance.
    return hmac.new(key, record, hashlib.sha256).hexdigest()

async def visibility_worker(queue: deque, mqtt_client: mqtt.Client):
    key = get_hmac_key()
    while True:
        batch = []
        start = time.time()
        while len(batch) < BATCH_SIZE and (time.time() - start) < BATCH_INTERVAL:
            try:
                batch.append(queue.popleft())
            except IndexError:
                await asyncio.sleep(0.01)
        if not batch:
            continue
        payload = json.dumps(batch, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        signature = sign_record(payload, key)
        envelope = json.dumps({"payload": batch, "sig": signature, "ts": time.time()})
        mqtt_client.publish(MQTT_TOPIC, envelope, qos=1)
        await asyncio.sleep(0)  # yield to event loop

def start_mqtt_client():
    c = mqtt.Client()
    c.tls_set()  # system CA; for production, pin broker certificate.
    c.connect("mqtt.example.city", 8883, keepalive=60)
    c.loop_start()
    return c

# Example: called by perception/decision pipeline
def enqueue_visibility(queue: deque, decision_id: str, inputs: dict, model_meta: dict, explanation: dict):
    # Minimal W3C PROV-like entry; avoid including raw sensitive PII.
    rec = {
        "id": decision_id,
        "ts": time.time(),
        "inputs": inputs,           # include hashes if inputs contain PII
        "model": model_meta,
        "explanation": explanation, # compact (e.g., top-3 features, saliency bounds)
    }
    queue.append(rec)

# Runtime orchestration
if __name__ == "__main__":
    queue = deque()
    mqtt = start_mqtt_client()
    loop = asyncio.get_event_loop()
    loop.create_task(visibility_worker(queue, mqtt))
    # The pipeline should call enqueue_visibility(...) per decision.
    loop.run_forever()