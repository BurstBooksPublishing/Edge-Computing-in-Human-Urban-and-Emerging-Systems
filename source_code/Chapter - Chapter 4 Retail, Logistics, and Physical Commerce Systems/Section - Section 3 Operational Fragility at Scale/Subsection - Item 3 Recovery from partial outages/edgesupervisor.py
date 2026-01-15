#!/usr/bin/env python3
"""Supervisor: monitor heartbeats, attempt in-band restart, escalate if needed."""
import time
import sqlite3
import json
import logging
from math import exp
import paho.mqtt.client as mqtt
from threading import Event, Thread

DB = "supervisor_state.db"
HEARTBEAT_TTL = 10.0  # seconds tolerated without heartbeat
MAX_ATTEMPTS = 5
ESCALATION_WEBHOOK = "https://ops.example.com/escalate"

logging.basicConfig(level=logging.INFO)

def init_db():
    conn = sqlite3.connect(DB, check_same_thread=False)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY,last_seen REAL,attempts INTEGER)")
    conn.commit()
    return conn

conn = init_db()
stop = Event()

def on_connect(client, userdata, flags, rc):
    client.subscribe("device/+/heartbeat")
    logging.info("MQTT connected, subscribed to heartbeats")

def on_message(client, userdata, msg):
    payload = msg.payload.decode()
    try:
        data = json.loads(payload)
        device_id = msg.topic.split("/")[1]
        now = time.time()
        conn.execute("INSERT OR REPLACE INTO devices(id,last_seen,attempts) VALUES(?,?,COALESCE((SELECT attempts FROM devices WHERE id=?),0))",
                     (device_id, now, device_id))
        conn.commit()
    except Exception:
        logging.exception("Invalid heartbeat payload")

def backoff_delay(attempt):
    # Exponential backoff with jitter ceiling
    base = 2.0**attempt
    return min(base + (0.1 * (attempt % 3)), 300)

def attempt_restart(client, device_id, attempt):
    # In-band restart via MQTT command topic
    cmd_topic = f"device/{device_id}/cmd"
    payload = json.dumps({"action":"restart-service","attempt":attempt})
    client.publish(cmd_topic, payload, qos=1)
    logging.info("Sent restart to %s attempt %d", device_id, attempt)

def escalate(device_id, last_seen):
    # Minimal escalation: log and send HTTP webhook (placeholder)
    logging.error("Escalating device %s last seen %s", device_id, time.ctime(last_seen))
    # Real code: requests.post(ESCALATION_WEBHOOK, json={...}) with retries

def monitor_loop(client):
    while not stop.is_set():
        now = time.time()
        rows = conn.execute("SELECT id,last_seen,attempts FROM devices").fetchall()
        for device_id, last_seen, attempts in rows:
            age = now - (last_seen or 0)
            if age <= HEARTBEAT_TTL:
                continue
            if attempts >= MAX_ATTEMPTS:
                escalate(device_id, last_seen)
                continue
            attempt = attempts + 1
            attempt_restart(client, device_id, attempt)
            delay = backoff_delay(attempt)
            # update attempt count and next expected check time
            conn.execute("UPDATE devices SET attempts=? WHERE id=?", (attempt, device_id))
            conn.commit()
            logging.info("Device %s age=%.1f attempts=%d backoff=%.1f", device_id, age, attempt, delay)
        time.sleep(1.0)

def main():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect("mqtt-broker.local", 1883, 60)
    client.loop_start()
    t = Thread(target=monitor_loop, args=(client,), daemon=True)
    t.start()
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        stop.set()
        client.loop_stop()
        conn.close()

if __name__ == "__main__":
    main()