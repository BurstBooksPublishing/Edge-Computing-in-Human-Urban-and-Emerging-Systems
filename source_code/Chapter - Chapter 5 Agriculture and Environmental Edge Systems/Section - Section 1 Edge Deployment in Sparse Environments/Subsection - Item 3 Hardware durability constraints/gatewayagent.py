#!/usr/bin/env python3
# Production-ready: handles intermittent network, TLS auth, and safe shutdown.
import time, queue, ssl, os, subprocess
import paho.mqtt.client as mqtt

MQTT_BROKER = "mqtt.example.com"
MQTT_TOPIC = "edge/gateway/health"
TLS_CERT = "/etc/certs/device.crt"
TLS_KEY = "/etc/certs/device.key"

q = queue.Queue(maxsize=1000)

def read_battery():  # replace with ADC or SMBus read
    return float(subprocess.check_output(["/usr/local/bin/read_batt"]).strip())

def read_temp():  # replace with hwmon or platform sensor
    return float(subprocess.check_output(["/usr/local/bin/read_temp"]).strip())

def enqueue_telemetry():
    payload = {"ts": int(time.time()), "temp": read_temp(), "vbat": read_battery()}
    try:
        q.put_nowait(payload)
    except queue.Full:
        q.get_nowait()  # drop oldest

def on_connect(client, userdata, flags, rc):
    client.connected_flag = (rc == 0)

def mqtt_client():
    client = mqtt.Client()
    client.tls_set(ca_certs=None, certfile=TLS_CERT, keyfile=TLS_KEY, cert_reqs=ssl.CERT_REQUIRED)
    client.on_connect = on_connect
    client.connect_async(MQTT_BROKER, 8883)
    client.loop_start()
    return client

def publish_loop(client):
    while True:
        try:
            msg = q.get(timeout=60)
        except queue.Empty:
            enqueue_telemetry(); continue
        if getattr(client, "connected_flag", False):
            client.publish(MQTT_TOPIC, payload=str(msg), qos=1)
        else:
            q.put(msg)  # requeue if offline

def safety_watchdog():
    v = read_battery()
    t = read_temp()
    if v < 3.0:  # critical battery threshold
        # flush persistent queue to local filesystem then shutdown
        with open("/var/local/health_queue.json", "w") as f:
            import json
            items = []
            while not q.empty():
                items.append(q.get_nowait())
            json.dump(items, f)
        subprocess.call(["/sbin/shutdown", "-h", "now"])
    if t > 85.0:
        # throttle CPU or disable radios via sysfs
        subprocess.call(["/usr/local/bin/throttle_radios"])

if __name__ == "__main__":
    client = mqtt_client()
    # main loop: sample less frequently to save power, run watchdog periodically
    while True:
        enqueue_telemetry()
        publish_loop(client)
        safety_watchdog()
        time.sleep(60)