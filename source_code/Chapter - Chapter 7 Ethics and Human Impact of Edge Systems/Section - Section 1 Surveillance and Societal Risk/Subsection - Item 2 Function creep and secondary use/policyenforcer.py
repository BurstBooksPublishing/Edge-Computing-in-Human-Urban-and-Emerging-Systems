import asyncio
import json
import jwt  # PyJWT, used to validate purpose-bound tokens
import aiohttp
import paho.mqtt.client as mqtt

MQTT_AUDIT_TOPIC = "city/audit/policy_decisions"
MQTT_BROKER = "mqtt.local"
JWT_PUBLIC_KEY = open("/etc/keys/jwt_pub.pem").read()

# Minimal policy: allowed purposed per device id
POLICY = {"camera-12": ["pedcount"], "camera-21": ["traffic"]}

def verify_token(token):
    # validate signature and expiry; returns claims dict
    return jwt.decode(token, JWT_PUBLIC_KEY, algorithms=["RS256"])

async def handle_incoming(payload, token):
    # payload: dict with device_id and data metadata
    claims = verify_token(token)
    purpose = claims.get("purpose")
    device = payload.get("device_id")
    allowed = POLICY.get(device, [])
    decision = {"device": device, "purpose": purpose, "allowed": purpose in allowed}
    # send audit
    client = mqtt.Client()
    client.connect(MQTT_BROKER)
    client.publish(MQTT_AUDIT_TOPIC, json.dumps(decision))
    client.disconnect()
    # enforce
    if decision["allowed"]:
        # forward minimal metadata to processing pipeline
        await forward_minimal(payload)
    else:
        # drop and optionally trigger local retention erase
        await trigger_local_erase(device)

async def forward_minimal(payload):
    # pseudo-code: forward only pre-approved fields
    minimal = {"device_id": payload["device_id"], "count": payload["count"], "ts": payload["ts"]}
    async with aiohttp.ClientSession() as session:
        await session.post("https://edge-process.local/ingest", json=minimal)

async def trigger_local_erase(device_id):
    # run secure erase on local store for device-specific buffer
    # actual implementation uses platform-specific secure-delete
    pass