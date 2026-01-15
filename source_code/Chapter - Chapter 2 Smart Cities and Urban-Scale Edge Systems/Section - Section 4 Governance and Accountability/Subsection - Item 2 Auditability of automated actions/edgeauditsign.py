#!/usr/bin/env python3
# Production-ready with pluggable key backend; replace `sign_data` with TPM/PKCS#11.
import json, time, os, hashlib, ssl
import paho.mqtt.client as mqtt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

DEVICE_ID = "traffic-node-42"            # configure per device (use secure provisioning)
LOCAL_LOG = "/var/audit/append_only.log" # place on FMAP partition or wear-leveled FS
MQTT_BROKER = "audit.municipality.local"
MQTT_TOPIC = f"audits/{DEVICE_ID}"

# Load or provision key (use TPM-backed key in production).
def load_private_key(path="/etc/keys/ecdsa.pem"):
    with open(path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)

# Sign bytes; in production call TPM_sign() instead.
def sign_data(private_key, data_bytes):
    sig = private_key.sign(data_bytes, ec.ECDSA(hashes.SHA256()))
    # encode DER to (r,s) if needed by verifier
    return sig

# Append-only write (fsync to reduce corruption risk).
def append_local(record_json):
    os.makedirs(os.path.dirname(LOCAL_LOG), exist_ok=True)
    with open(LOCAL_LOG, "ab") as f:                 # append-only semantics
        f.write(record_json.encode("utf-8") + b"\n")
        f.flush()
        os.fsync(f.fileno())

# Compute hash-chain element per Eq. (1).
def compute_chain_hash(prev_hash_hex, action_bytes):
    h = hashlib.sha256()
    h.update(action_bytes)
    h.update(bytes.fromhex(prev_hash_hex))
    return h.hexdigest()

# MQTT client with TLS.
def mqtt_publish(client, topic, payload):
    client.publish(topic, payload, qos=1)

def main():
    priv = load_private_key()
    prev_hash = "00"*32  # IV: zeroed 32-byte hex for first entry
    client = mqtt.Client()
    client.tls_set(ca_certs="/etc/ssl/certs/ca.pem",
                   certfile=None, keyfile=None,
                   tls_version=ssl.PROTOCOL_TLS_CLIENT)
    client.connect(MQTT_BROKER, 8883)
    client.loop_start()

    # Example action: traffic phase change
    action = {"actor":"controller_v1","action":"phase_change","phase":"NS_GREEN",
              "ts":int(time.time()), "inputs":{"queue_ns":12,"queue_ew":3}}
    action_bytes = json.dumps(action, sort_keys=True).encode("utf-8")
    chain_hash = compute_chain_hash(prev_hash, action_bytes)
    signed = sign_data(priv, bytes.fromhex(chain_hash))  # sign chain hash
    record = {"device": DEVICE_ID, "action": action, "chain_hash": chain_hash,
              "signature": signed.hex(), "pub_key_id":"ecdsa-pub-2025"}
    payload = json.dumps(record, sort_keys=True)
    append_local(payload)          # durable local evidence
    mqtt_publish(client, MQTT_TOPIC, payload)  # remote copy for federation
    prev_hash = chain_hash

if __name__ == "__main__":
    main()