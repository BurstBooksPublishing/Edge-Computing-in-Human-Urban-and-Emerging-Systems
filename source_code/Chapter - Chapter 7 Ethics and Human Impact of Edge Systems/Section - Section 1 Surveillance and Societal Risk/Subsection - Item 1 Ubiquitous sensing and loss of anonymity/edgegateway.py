#!/usr/bin/env python3
import cv2
import time
import json
import paho.mqtt.client as mqtt
import numpy as np
from hashlib import sha256

BROKER = "mqtt.example.local"
TOPIC = "edge/aggregates"
CAM_INDEX = 0
LAPLACE_SCALE = 1.0  # privacy parameter; tune per policy

def laplace_noise(scale):
    u = np.random.uniform(-0.5, 0.5)
    return -scale * np.sign(u) * np.log(1 - 2*abs(u))

def publish_count(client, count):
    payload = {"timestamp": time.time(), "count": int(count)}
    client.publish(TOPIC, json.dumps(payload), qos=1)

def blur_faces(frame, face_cascade):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.1, 4)
    for (x,y,w,h) in faces:
        roi = frame[y:y+h, x:x+w]
        k = (w//7)|1
        frame[y:y+h, x:x+w] = cv2.GaussianBlur(roi, (k,k), 0)
    return frame, len(faces)

def hash_frame_meta(count, ts):
    return sha256(f"{count}|{ts:.1f}".encode()).hexdigest()

def main():
    client = mqtt.Client()
    client.tls_set()  # use system CA, require broker TLS
    client.username_pw_set("edge_module", "REPLACE_WITH_SECRET")  # use vault in prod
    client.connect(BROKER, 8883, keepalive=60)
    cap = cv2.VideoCapture(CAM_INDEX)
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    if not cap.isOpened():
        raise SystemExit("Camera not available")
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.1); continue
            frame, faces = blur_faces(frame, face_cascade)
            # aggregate and privatize count
            noisy = max(0, faces + laplace_noise(LAPLACE_SCALE))
            ts = time.time()
            # publish only aggregate; store hash for audit
            publish_count(client, noisy)
            audit_hash = hash_frame_meta(noisy, ts)
            # write minimal audit to local secure storage (append-only)
            with open("/var/log/edge_audit.log", "a") as f:
                f.write(f"{ts},{audit_hash}\n")
            time.sleep(1.0)  # control sampling rate to limit correlation
    finally:
        cap.release()
        client.disconnect()

if __name__ == "__main__":
    main()