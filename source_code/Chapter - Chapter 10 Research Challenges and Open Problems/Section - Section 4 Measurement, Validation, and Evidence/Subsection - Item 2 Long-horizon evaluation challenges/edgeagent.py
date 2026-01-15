#!/usr/bin/env python3
# Minimal, production-ready telemetry agent for edge nodes.
import sqlite3, json, time, hmac, hashlib, socket
import paho.mqtt.client as mqtt

DB = "/var/lib/edge_telemetry/telemetry.db"
BROKER = "mqtt.example.city:8883"
TOPIC = "city/edge/telemetry"
HMAC_KEY = b"REPLACE_WITH_SECURE_KEY"

# init local DB (durable buffer)
conn = sqlite3.connect(DB, timeout=30)
conn.execute("CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY, payload TEXT, ts INTEGER)")
conn.commit()

def sign(payload: bytes) -> str:
    return hmac.new(HMAC_KEY, payload, hashlib.sha256).hexdigest()

def collect_summary():
    # Collect compact summary: runtime, temp, model_accuracy_estimate
    return {
        "ts": int(time.time()),
        "host": socket.gethostname(),
        "cpu_temp_c": read_cpu_temp(),      # platform-specific helper
        "net_rtt_ms": measure_rtt("8.8.8.8"),
        "local_score": estimate_local_score() # periodic self-test
    }

def enqueue(payload: dict):
    conn.execute("INSERT INTO outbox(payload,ts) VALUES(?,?)", (json.dumps(payload), payload["ts"]))
    conn.commit()

def publish_loop():
    client = mqtt.Client()
    client.tls_set()  # use system CAs
    client.connect("mqtt.example.city", port=8883)
    client.loop_start()
    backoff = 1
    while True:
        rows = conn.execute("SELECT id,payload FROM outbox ORDER BY id LIMIT 20").fetchall()
        if not rows:
            time.sleep(30); continue
        for rid,p in rows:
            payload = json.loads(p)
            payload_bytes = json.dumps(payload, separators=(",",":")).encode()
            payload["sig"] = sign(payload_bytes)
            try:
                client.publish(TOPIC, json.dumps(payload), qos=1)
                conn.execute("DELETE FROM outbox WHERE id=?", (rid,))
                conn.commit()
                backoff = 1
            except Exception:
                time.sleep(backoff); backoff = min(300, backoff*2)
                break
    client.loop_stop()

# Periodic collection loop (run under systemd or container)
if __name__ == "__main__":
    while True:
        s = collect_summary()
        enqueue(s)
        time.sleep(300)  # sample every 5 minutes