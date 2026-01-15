#!/usr/bin/env python3
# Minimal production-ready edge agent for selective disclosure
import json, time, hashlib
import paho.mqtt.client as mqtt
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

# Load device private key (stored in TPM or secure file system in production)
with open('/etc/edge/key.pem','rb') as kf:
    private_key = serialization.load_pem_private_key(kf.read(), password=None)

MQTT_BROKER = "mqtt.example.local"
TOPIC = "city/transport/summary"

def summarize(sensor_batch):
    # compute short-lived summary; drop raw frames to minimize V
    count = len(sensor_batch); avg_speed = sum(s['speed'] for s in sensor_batch)/count
    return {'timestamp': int(time.time()), 'count': count, 'avg_speed': avg_speed}

def sign_payload(payload: bytes) -> bytes:
    # RSA-PSS signing; replace with TPM signing API in production
    return private_key.sign(payload, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH), hashes.SHA256())

def publish_summary(summary):
    payload = json.dumps(summary).encode('utf-8')
    signature = sign_payload(payload)
    envelope = {'payload': summary, 'sig': signature.hex()}
    client = mqtt.Client()
    client.tls_set(ca_certs="/etc/edge/ca.pem", certfile="/etc/edge/cert.pem", keyfile="/etc/edge/key.pem")
    client.connect(MQTT_BROKER, 8883, 60)
    client.publish(TOPIC, json.dumps(envelope), qos=1)
    client.disconnect()

# Example runtime loop (integrate with Zephyr/FreeRTOS sensors on MCUs)
if __name__ == "__main__":
    while True:
        # sensor_batch would come from on-device pipeline; raw data discarded after summarize()
        sensor_batch = [{'speed': 12.3},{'speed': 15.1},{'speed': 11.8}]
        summary = summarize(sensor_batch)
        publish_summary(summary)
        time.sleep(30)  # throttle to balance energy and timeliness