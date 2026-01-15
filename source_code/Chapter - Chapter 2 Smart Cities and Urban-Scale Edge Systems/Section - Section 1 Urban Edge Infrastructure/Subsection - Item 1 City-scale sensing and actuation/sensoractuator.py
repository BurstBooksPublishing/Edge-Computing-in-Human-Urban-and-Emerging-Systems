#!/usr/bin/env python3
"""
Production-ready script:
- computes required sensor density for coverage target
- simulates sensor events and publishes actuation messages
- includes TLS, reconnection backoff, and rate limiting
"""
import math
import asyncio
import json
import ssl
import random
import time
from paho.mqtt import client as mqtt

# Configuration (move to secure config store in production)
BROKER = "mqtt.example.city"
PORT = 8883
TOPIC = "city/intersection/actuate"
CLIENT_ID = "edge-controller-01"
TLS_CERT = "/etc/ssl/certs/ca.pem"  # CA bundle path
L_MAX_MS = 150  # actuation deadline in ms

def required_density(r_meters: float, p_target: float) -> float:
    """Return sensor density lambda for radius r and coverage p_target."""
    if not 0 < p_target < 1:
        raise ValueError("p_target must be in (0,1)")
    return -math.log(1.0 - p_target) / (math.pi * r_meters * r_meters)

async def simulate_and_publish(num_sensors: int, publish_rate_hz: float):
    """Simulate sensors, detect events, and publish secure actuation commands."""
    # Setup TLS MQTT client with reconnect/backoff
    client = mqtt.Client(client_id=CLIENT_ID, clean_session=True)
    client.tls_set(TLS_CERT, certfile=None, keyfile=None, tls_version=ssl.PROTOCOL_TLS_CLIENT)
    client.tls_insecure_set(False)
    client.max_inflight_messages_set(20)
    # synchronous loop running in executor to maintain reliability
    loop = asyncio.get_running_loop()
    backoff = 1.0
    while True:
        try:
            client.connect(BROKER, PORT, keepalive=60)
            client.loop_start()
            break
        except Exception:
            await asyncio.sleep(backoff)
            backoff = min(30.0, backoff * 2.0)
    # Simulate sensors reporting and local edge decision
    interval = 1.0 / publish_rate_hz
    while True:
        start = time.monotonic()
        # Randomly choose a sensor and simulate detection confidence
        sensor_id = random.randrange(num_sensors)
        confidence = random.random()
        # Local decision rule: act only if confidence exceeds threshold
        if confidence > 0.85:
            msg = {
                "sensor": sensor_id,
                "ts": time.time(),
                "confidence": confidence,
                "deadline_ms": L_MAX_MS
            }
            # Publish with QoS 1 for at-least-once delivery
            client.publish(TOPIC, payload=json.dumps(msg), qos=1)
        # Rate limiting and deadline awareness
        elapsed = time.monotonic() - start
        await asyncio.sleep(max(0.0, interval - elapsed))
    # Cleanup (never reached in many edge loops)
    client.loop_stop()
    client.disconnect()

if __name__ == "__main__":
    # Example: coverage of 95% with sensors reaching 30 m
    lambda_req = required_density(r_meters=30.0, p_target=0.95)
    num_sensors_area = int(math.ceil(lambda_req * 10000))  # for 1 ha
    # Run simulation: sensors within local edge cluster
    asyncio.run(simulate_and_publish(num_sensors_area, publish_rate_hz=10.0))