#!/usr/bin/env python3
import time, logging, requests, json
import paho.mqtt.client as mqtt

# config
MQTT_BROKER = "localhost"
MQTT_TOPIC = "farm/nodes/+/telemetry"
MENDER_API = "https://mender.example.com/api/management/v1/deployments/deployments"
OTA_MIN_SOC = 0.5          # schedule OTA only if SOC >= 50%
IRRADIANCE_MIN = 200       # W/m^2 threshold
RISK_THRESHOLD = 0.7
SMOOTH_ALPHA = 0.2

# in-memory state
state = {}  # node_id -> {'soc':..., 'irr':..., 'risk':...}

logging.basicConfig(level=logging.INFO)

def smooth(prev, value):
    return SMOOTH_ALPHA*value + (1-SMOOTH_ALPHA)*(prev or value)

def schedule_ota(node_id):
    # trigger Mender deployment for device; token must be provisioned
    payload = {"device_filter": {"id": node_id}, "artifact_name": "edge-firmware:v1.2.3"}
    try:
        r = requests.post(MENDER_API, json=payload, timeout=10)  # auth via env/token mgmt
        r.raise_for_status()
        logging.info("OTA scheduled for %s", node_id)
    except Exception as e:
        logging.error("OTA failed for %s: %s", node_id, e)

def handle_telemetry(node_id, msg):
    soc = msg.get("battery_soc")
    irr = msg.get("irradiance")
    errs = msg.get("error_count", 0)

    s = state.setdefault(node_id, {})
    s['soc'] = soc
    s['irr'] = irr
    s['risk'] = smooth(s.get('risk'), errs/ max(1, msg.get("uptime_hours",1)))

    # energy-aware OTA decision
    if s['soc'] >= OTA_MIN_SOC and s['irr'] >= IRRADIANCE_MIN and s['risk'] < RISK_THRESHOLD:
        schedule_ota(node_id)
    elif s['risk'] >= RISK_THRESHOLD:
        logging.warning("High maintenance risk for %s: risk=%.2f", node_id, s['risk'])
        # create technician ticket (integration point)
        # post_ticket(node_id, s)

def on_message(client, userdata, m):
    try:
        topic = m.topic.split('/')
        node_id = topic[2]
        payload = json.loads(m.payload.decode())
        handle_telemetry(node_id, payload)
    except Exception as e:
        logging.exception("Failed to handle message: %s", e)

def main():
    client = mqtt.Client()
    client.on_message = on_message
    client.connect(MQTT_BROKER)
    client.subscribe(MQTT_TOPIC)
    client.loop_forever()

if __name__ == "__main__":
    main()