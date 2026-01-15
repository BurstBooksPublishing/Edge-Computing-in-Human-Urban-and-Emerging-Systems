import json, time, ssl
from paho.mqtt import client as mqtt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import hashes

# load private key from secure storage (TPM-backed key recommended)
with open("/etc/edge/keys/ed25519_priv.pem","rb") as f:
    priv = serialization.load_pem_private_key(f.read(), password=None)

def sign_trace(trace: dict) -> dict:
    trace_bytes = json.dumps(trace, sort_keys=True).encode("utf-8")
    sig = priv.sign(trace_bytes)  # Ed25519 signature
    trace["signature"] = sig.hex()
    return trace

def publish_trace(trace: dict):
    client = mqtt.Client(client_id="edge-node-01")
    client.tls_set(ca_certs="/etc/edge/ca.pem", certfile=None, keyfile=None, tls_version=ssl.PROTOCOL_TLSv1_2)
    client.tls_insecure_set(False)
    client.connect("mqtt.example.city.local", 8883)
    client.loop_start()
    client.publish("provenance/traces", json.dumps(trace), qos=1)
    client.loop_stop()

# compose minimal provenance event
event = {
    "device": "tram-az1",                 # use \lstinline|device| to avoid raw underscores
    "module": "perception.v2",
    "timestamp": time.time(),             # prefer PTP-synced time
    "span_id": "span-12345",
    "event": "brake_command",
    "metadata": {"confidence":0.12, "frame_id":"cam-0/2025-12-29T12:00:01Z"}
}

signed = sign_trace(event)
publish_trace(signed)