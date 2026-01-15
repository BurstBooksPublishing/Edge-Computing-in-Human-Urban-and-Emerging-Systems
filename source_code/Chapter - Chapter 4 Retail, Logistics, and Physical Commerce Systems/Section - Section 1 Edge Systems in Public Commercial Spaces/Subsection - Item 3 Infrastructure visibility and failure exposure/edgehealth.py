#!/usr/bin/env python3
# Production-ready: TLS, reconnect, simple checks, configurable by env
import os, time, json, socket, ssl
import paho.mqtt.client as mqtt
import psutil
import onnxruntime as rt

BROKER = os.getenv("MQTT_BROKER","broker.example.local")
PORT = int(os.getenv("MQTT_PORT","8883"))
CLIENT_ID = os.getenv("CLIENT_ID","edge-node-001")
CERT = os.getenv("TLS_CERT","/etc/ssl/certs/device.crt")
KEY = os.getenv("TLS_KEY","/etc/ssl/private/device.key")
CA = os.getenv("TLS_CA","/etc/ssl/certs/ca.pem")
TOPIC = f"edge/health/{CLIENT_ID}"
MODEL_PATH = os.getenv("MODEL_PATH","/opt/models/health_probe.onnx")

# prepare ONNX session; failure here is a visibility signal
try:
    sess = rt.InferenceSession(MODEL_PATH, providers=['CPUExecutionProvider'])
except Exception as e:
    sess = None

client = mqtt.Client(client_id=CLIENT_ID)
client.tls_set(ca_certs=CA, certfile=CERT, keyfile=KEY, tls_version=ssl.PROTOCOL_TLSv1_2)
client.tls_insecure_set(False)

def publish(payload):
    client.publish(TOPIC, json.dumps(payload), qos=1)

def measure_inference_latency():
    if not sess: return None
    import numpy as np
    dummy = {sess.get_inputs()[0].name: (np.zeros(sess.get_inputs()[0].shape).astype('float32'))}
    t0 = time.time(); sess.run(None, dummy); return time.time()-t0

client.connect(BROKER, PORT)
client.loop_start()

backoff = 1
while True:
    try:
        payload = {
            "ts": time.time(),
            "uptime": int(time.time() - psutil.boot_time()),
            "cpu_pct": psutil.cpu_percent(interval=0.5),
            "mem_pct": psutil.virtual_memory().percent,
            "temp_c": psutil.sensors_temperatures().get('cpu-thermal',[{"current":None}])[0]["current"],
            "inf_latency": measure_inference_latency()
        }
        publish(payload)
        backoff = 1
        time.sleep(5)  # telemetry cadence; tune for bandwidth/energy
    except (socket.error, ssl.SSLError, mqtt.WebsocketConnectionError):
        time.sleep(backoff)
        backoff = min(backoff*2, 300)