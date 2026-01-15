#!/usr/bin/env python3
import json, time, hashlib
from nacl.signing import SigningKey
import sqlite3, paho.mqtt.client as mqtt

# Load signing key (replace with TPM-backed retrieval in production)
with open("/etc/keys/ed25519_seed.bin","rb") as f:
    seed = f.read()
signing_key = SigningKey(seed)

# Local append-only DB for audit records
db = sqlite3.connect("/var/lib/edge_audit/audit.db", isolation_level=None)
db.execute("CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, record JSON, hash TEXT)")

MQTT_BROKER="broker.city.example:8883"
client = mqtt.Client()
client.tls_set()  # use system CA; configure client certs for mutual TLS if needed
client.connect("broker.city.example", 8883)

def sha256_hex(b):
    return hashlib.sha256(b).hexdigest()

def append_and_publish(decision, inputs_meta, model_meta):
    ts = time.time()
    prev = db.execute("SELECT hash FROM audit ORDER BY id DESC LIMIT 1").fetchone()
    prev_hash = prev[0] if prev else "0"*64

    record = {
        "timestamp": ts,
        "inputs": inputs_meta,        # e.g., sensor IDs, digests
        "model": model_meta,          # model id, version, weights hash
        "decision": decision,         # action and parameters
        "prev_hash": prev_hash
    }
    raw = json.dumps(record, separators=(",",":"), sort_keys=True).encode()
    record_hash = sha256_hex(raw)
    signature = signing_key.sign(raw).signature.hex()

    stored = {
        "record": record,
        "hash": record_hash,
        "signature": signature
    }
    # durable append
    db.execute("INSERT INTO audit(record,hash) VALUES (?,?)", (json.dumps(stored), record_hash))
    # publish only digest to minimize bandwidth
    client.publish("city/edges/audit/digest", json.dumps({
        "id_hash": record_hash,
        "timestamp": ts,
        "signature": signature
    }), qos=1, retain=False)

# Example invocation
decision = {"action":"extend_green","duration_s":7}
inputs_meta = {"camera":"cam-12:frame_4532:sha256:...","radar":"rad-7:count:12"}
model_meta = {"name":"traffic_priority_v1","version":"2025-06-10","weights_sha256":"..."}
append_and_publish(decision, inputs_meta, model_meta)