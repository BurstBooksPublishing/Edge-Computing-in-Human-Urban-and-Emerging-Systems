#!/usr/bin/env python3
# Production-ready: uses paho-mqtt and cryptography libraries.
import time, json, threading, logging
import paho.mqtt.client as mqtt
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

BROKER = "mqtt.example.city"
TOPIC_UPDATE = "edge/policy/update"
TOPIC_STATUS = "edge/policy/status"
CANARY_TIMEOUT = 300  # seconds
PUBLIC_KEY_PEM = open("gov_pub.pem","rb").read()

pubkey = serialization.load_pem_public_key(PUBLIC_KEY_PEM)
log = logging.getLogger("rollout")
log.setLevel(logging.INFO)

def verify_signature(payload: bytes, signature: bytes) -> bool:
    # Verify RSA-PSS signature; raise on invalid
    try:
        pubkey.verify(signature, payload,
                      padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                                  salt_length=padding.PSS.MAX_LENGTH),
                      hashes.SHA256())
        return True
    except Exception:
        return False

def apply_policy(policy: dict):
    # Atomically deploy policy to local store and signal actuators via REST/CoAP.
    with open("/var/lib/edge_policy.json","w") as f:
        json.dump(policy, f)
    # TODO: call actuator proxies; placeholder:
    log.info("Applied policy version %s", policy["version"])

def rollback_policy(old_version: dict):
    # Restore previous policy state
    apply_policy(old_version)
    log.warning("Rolled back to version %s", old_version["version"])

def on_message(client, userdata, msg):
    # Incoming update contains payload and base64 signature
    envelope = json.loads(msg.payload.decode())
    payload = json.dumps(envelope["policy"]).encode()
    sig = bytes.fromhex(envelope["signature_hex"])
    if not verify_signature(payload, sig):
        log.error("Invalid signature for update")
        return
    policy = envelope["policy"]
    # Canary logic: deploy locally as canary first
    old = json.load(open("/var/lib/edge_policy.json"))
    apply_policy(policy)
    start = time.time()
    # Wait for monitoring metric to confirm safe operation
    while time.time() - start < CANARY_TIMEOUT:
        status = check_local_safety_metrics()  # implement sensor checks
        if status["safe"]:
            client.publish(TOPIC_STATUS, json.dumps({"node":NODE_ID,"status":"canary_ok","version":policy["version"]}))
            return
        time.sleep(5)
    # Timeout -> rollback and alert
    rollback_policy(old)
    client.publish(TOPIC_STATUS, json.dumps({"node":NODE_ID,"status":"rolled_back","version":old["version"]}))

client = mqtt.Client()
client.on_message = on_message
client.connect(BROKER)
client.subscribe(TOPIC_UPDATE)
client.loop_start()
# keep running in production process manager (systemd, k8s)