import asyncio
import json
import sqlite3
from datetime import datetime
from asyncio_mqtt import Client, MqttError
import aiohttp
import backoff

DB_PATH = "/var/lib/incident_queue.db"
MQTT_BROKER = "mec.local"
MQTT_TOPIC = "incident/alerts"
DISPATCHER_URL = "https://dispatcher.city/api/v1/dispatch"
TLS_PARAMS = {"cert": "/etc/ssl/cert.pem"}  # example TLS parameters

# durable simple queue using SQLite
def init_db():
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    conn.execute("CREATE TABLE IF NOT EXISTS q(id INTEGER PRIMARY KEY, priority INTEGER, payload TEXT, ts TEXT)")
    return conn

def enqueue(conn, priority, payload):
    conn.execute("INSERT INTO q(priority, payload, ts) VALUES (?, ?, ?)",
                 (priority, json.dumps(payload), datetime.utcnow().isoformat()))

def dequeue(conn):
    row = conn.execute("SELECT id, priority, payload FROM q ORDER BY priority DESC, id ASC LIMIT 1").fetchone()
    if row:
        conn.execute("DELETE FROM q WHERE id=?", (row[0],))
        return json.loads(row[2])
    return None

@backoff.on_exception(backoff.expo, Exception, max_time=300)
async def forward_to_dispatch(payload):
    async with aiohttp.ClientSession() as session:
        async with session.post(DISPATCHER_URL, json=payload, timeout=10) as resp:
            resp.raise_for_status()
            return await resp.json()

async def worker(conn):
    while True:
        item = dequeue(conn)
        if not item:
            await asyncio.sleep(0.5)
            continue
        try:
            await forward_to_dispatch(item)
        except Exception:
            # re-enqueue with slightly lower priority to avoid starvation
            enqueue(conn, item.get("priority", 0)-1, item)
            await asyncio.sleep(1)

async def mqtt_loop(conn):
    reconnect_interval = 1
    while True:
        try:
            async with Client(MQTT_BROKER, tls_context=None) as client:  # configure TLS in production
                async with client.filtered_messages(MQTT_TOPIC) as messages:
                    await client.subscribe(MQTT_TOPIC, qos=1)
                    async for msg in messages:
                        try:
                            payload = json.loads(msg.payload.decode())
                            # payload must include 'priority' and 'incident' fields
                            enqueue(conn, int(payload.get("priority", 0)), payload)
                        except Exception:
                            continue
        except MqttError:
            await asyncio.sleep(reconnect_interval)
            reconnect_interval = min(reconnect_interval * 2, 30)

async def main():
    conn = init_db()
    await asyncio.gather(mqtt_loop(conn), worker(conn))

if __name__ == "__main__":
    asyncio.run(main())