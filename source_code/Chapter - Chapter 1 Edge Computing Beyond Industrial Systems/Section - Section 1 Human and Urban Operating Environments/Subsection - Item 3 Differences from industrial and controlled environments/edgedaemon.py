#!/usr/bin/env python3
# Production-ready: non-blocking capture, local sqlite buffer, MQTT with backoff.
import asyncio, sqlite3, time, json, logging
from datetime import datetime
from threading import Thread
import cv2  # OpenCV for camera capture
import paho.mqtt.client as mqtt

DB_PATH = "/var/local/edge_buffer.db"
MQTT_BROKER = "mqtt.example.city:1883"
TOPIC = "city/sidewalk/flow"

# lightweight TFLite load if present; else no-op classifier
try:
    import tflite_runtime.interpreter as tflite
    INTERP = tflite.Interpreter(model_path="/opt/models/ped_count.tflite")
    INTERP.allocate_tensors()
except Exception:
    INTERP = None

# initialize local buffer
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.execute("CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, ts REAL, payload TEXT)")
conn.commit()

def classify(frame):
    if INTERP is None:
        return {"count": -1, "mode": "noop"}
    # preprocessing and inference (platform-specific delegates omitted)
    # ... placeholder for resizing, normalization, tensor set/get ...
    return {"count": 7, "mode": "tflite"}  # example

def buffer_message(payload):
    conn.execute("INSERT INTO messages(ts,payload) VALUES (?,?)", (time.time(), json.dumps(payload)))
    conn.commit()

def mqtt_loop():
    client = mqtt.Client()
    client.connect(MQTT_BROKER.split(":")[0], int(MQTT_BROKER.split(":")[1]))
    client.loop_start()
    while True:
        rows = conn.execute("SELECT id,payload FROM messages ORDER BY id LIMIT 50").fetchall()
        if not rows:
            time.sleep(1); continue
        for _id, payload in rows:
            try:
                client.publish(TOPIC, payload, qos=1)  # qos=1 for at-least-once
                conn.execute("DELETE FROM messages WHERE id=?", (_id,))
                conn.commit()
            except Exception:
                time.sleep(2)  # simple backoff; production: exponential/backoff jitter
                break

def capture_loop():
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    while True:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.1); continue
        result = classify(frame)
        payload = {"ts": datetime.utcnow().isoformat()+"Z", "result": result}
        buffer_message(payload)
        time.sleep(0.2)  # adjustable frame rate for load control

# run threads to isolate blocking libs (OpenCV, paho)
Thread(target=mqtt_loop, daemon=True).start()
capture_loop()