#!/usr/bin/env python3
# Production-ready: asyncio MQTT client, signed audit log, timeout arbitration.
import asyncio, json, time, hashlib, os
from paho.mqtt import client as mqtt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from aiohttp import web

# Load keypair from secure element or protected file (example: ed25519)
with open('/etc/keys/edge_priv.pem','rb') as f:
    priv = serialization.load_pem_private_key(f.read(), password=None)
pub = priv.public_key()

LOG_PATH = '/var/log/edge_audit.chain'
MQTT_BROKER = 'mqtt.local'
WATCHDOG_SECONDS = 10.0

def append_chain(record: dict):
    # Append-only chained log: prev_hash || json || timestamp || signature
    prev = ''
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH,'rb') as f:
            prev = f.read().split(b'\n')[-2]  # previous hash line
    payload = json.dumps(record, separators=(',',':')).encode()
    h = hashlib.sha256(prev + payload + str(time.time()).encode()).hexdigest()
    sig = priv.sign(h.encode()).hex()
    with open(LOG_PATH,'ab') as f:
        f.write(payload + b'\n' + h.encode() + b'\n' + sig.encode() + b'\n')

# MQTT client setup
client = mqtt.Client(client_id="edge_arbiter")
client.tls_set()  # system CA; use certs configured via provisioning
client.connect(MQTT_BROKER, 8883)

async def notify_attendant(exception_payload: dict):
    # Publish minimal context for fast human decision
    topic = f'ops/alerts/{exception_payload["station_id"]}'
    client.publish(topic, json.dumps(exception_payload), qos=1)
    append_chain({"event":"alert_sent","payload":exception_payload})

async def await_ack(station_id: str, timeout: float):
    # Wait for external acknowledgement via REST webhook
    future = asyncio.get_event_loop().create_future()
    async def ack_handler(request):
        body = await request.json()
        if body.get('station_id') == station_id:
            future.set_result(body)
            return web.Response(text='ack received')
        return web.Response(status=400)
    app = web.Application()
    app.router.add_post('/ack', ack_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8081)
    await site.start()
    try:
        return await asyncio.wait_for(future, timeout)
    except asyncio.TimeoutError:
        return None
    finally:
        await runner.cleanup()

async def handle_exception(exc: dict):
    await notify_attendant(exc)
    ack = await await_ack(exc['station_id'], WATCHDOG_SECONDS)
    if ack:
        # human validated; apply action and log
        append_chain({"event":"human_override","station":exc['station_id'],"ack":ack})
        # send command to actuator controller (example, simplified)
        client.publish(f'control/{exc["station_id"]}', json.dumps({"action":"unblock"}), qos=1)
    else:
        # fail-safe deterministic action
        append_chain({"event":"fail_safe","station":exc['station_id']})
        client.publish(f'control/{exc["station_id"]}', json.dumps({"action":"lock"}), qos=1)

# Example entrypoint for exception raised by perception pipeline
if __name__ == '__main__':
    sample_exc = {"station_id":"S1","type":"low_confidence","confidence":0.42,"image_uri":"/tmp/crop.jpg"}
    asyncio.run(handle_exception(sample_exc))