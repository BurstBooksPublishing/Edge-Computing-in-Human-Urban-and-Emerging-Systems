#!/usr/bin/env python3
# Production-ready: TLS, QoS, reconnects, small CRDT (LWW-register)
import ssl, time, json, socket
import ntplib
import paho.mqtt.client as mqtt

BROKER = "edge-mosquitto.local"
PORT = 8883
TOPIC = "city/arpins/state"            # shared object topic
CLIENT_ID = "client-jetson-01"
TLS_PARAMS = {"ca_certs":"ca.pem","certfile":"client.pem","keyfile":"client.key"}

# get monotonic NTP offset (seconds)
def ntp_offset(server="pool.ntp.org"):
    try:
        c = ntplib.NTPClient()
        r = c.request(server, version=4, timeout=2)
        return r.offset
    except Exception:
        return 0.0

OFFSET = ntp_offset()                  # application-level clock correction

# LWW-register: value plus wall-clock timestamp
def make_msg(value):
    return json.dumps({"value":value, "ts": time.time() + OFFSET, "id": CLIENT_ID})

state = {"value": None, "ts": 0.0}

def on_connect(client, userdata, flags, rc):
    client.subscribe(TOPIC, qos=1)

def on_message(client, userdata, msg):
    global state
    try:
        payload = json.loads(msg.payload.decode())
        if payload["ts"] > state["ts"]:
            state = {"value": payload["value"], "ts": payload["ts"]}
            # apply state to local scene (e.g., AR overlay update)
            apply_state(state)
    except Exception:
        pass

def apply_state(s):
    # Replace with platform-specific rendering or actuator code
    print(f"Applied state: {s['value']} (ts={s['ts']:.6f})")

def publish_value(client, value):
    client.publish(TOPIC, make_msg(value), qos=1)

# MQTT client setup
client = mqtt.Client(client_id=CLIENT_ID, clean_session=True)
client.tls_set(**TLS_PARAMS)
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, PORT, keepalive=30)
client.loop_start()

# Example usage: update state on local event
publish_value(client, {"annotation":"Historic fountain", "pos":[12.34,56.78]})
time.sleep(1)
client.loop_stop()
client.disconnect()