import json, time, requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

# Load device private key (PEM), stored in device TPM or secure storage in production.
with open('/etc/keys/device_key.pem', 'rb') as f:
    PRIVATE_KEY = serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())

DEVICE_ID = "edge.node.001"
COLLECTOR = "https://collector.city.example/audit"

def sign_event(event: dict) -> dict:
    event_bytes = json.dumps(event, sort_keys=True, separators=(',',':')).encode('utf-8')
    sig = PRIVATE_KEY.sign(
        event_bytes,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256()
    )
    return {"event": event, "signature": sig.hex(), "device_id": DEVICE_ID}

def transmit(signed: dict, max_retries=5):
    for attempt in range(max_retries):
        try:
            resp = requests.post(COLLECTOR, json=signed, timeout=5)
            resp.raise_for_status()
            return True
        except Exception:
            time.sleep(2 ** attempt)  # exponential backoff
    # On persistent failure, write to durable local queue for later ingestion.
    with open('/var/local/audit_queue.log', 'ab') as q:
        q.write(json.dumps(signed).encode('utf-8') + b'\n')
    return False

# Example usage: sign a sensor-triggered actuation event.
evt = {"ts": time.time(), "sensor": "camera_12", "action": "green_command", "reason": "pedestrian_clear"}
signed_evt = sign_event(evt)
transmit(signed_evt)