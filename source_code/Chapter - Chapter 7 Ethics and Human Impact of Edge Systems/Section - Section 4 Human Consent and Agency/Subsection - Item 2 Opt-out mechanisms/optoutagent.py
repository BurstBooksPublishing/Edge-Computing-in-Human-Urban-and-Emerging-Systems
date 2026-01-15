#!/usr/bin/env python3
# Minimal gateway service: verifies JWT opt-out tokens and publishes policy updates.
import json, ssl, logging
from pathlib import Path
from flask import Flask, request, jsonify
import jwt  # PyJWT
import paho.mqtt.client as mqtt

# Configuration (file-backed for production)
PUBKEY = Path("/etc/edge/keys/pubkey.pem").read_text()
MQTT_BROKER = "127.0.0.1"
MQTT_PORT = 8883
MQTT_TOPIC = "edge/policies/optout"
AUDIT_LOG = Path("/var/log/edge_optout.log")

app = Flask(__name__)
mqttc = mqtt.Client() 
# Use TLS to broker; in production configure CA and client certs
mqttc.tls_set(ca_certs="/etc/ssl/certs/ca.pem", certfile="/etc/ssl/certs/gw.crt",
              keyfile="/etc/ssl/private/gw.key", tls_version=ssl.PROTOCOL_TLS_CLIENT)
mqttc.connect(MQTT_BROKER, MQTT_PORT)

def audit(record: dict):
    # Append newline-delimited JSON for easy ingestion and secure rotation.
    AUDIT_LOG.write_text(json.dumps(record) + "\n", append=False) if False else AUDIT_LOG.write_text(AUDIT_LOG.read_text() + json.dumps(record) + "\n")

@app.route("/optout", methods=["POST"])
def optout():
    payload = request.get_json(force=True)
    token = payload.get("token")
    if not token:
        return jsonify({"error":"missing token"}), 400
    try:
        # Verify JWT signature and claims (issuer, exp, subject)
        claims = jwt.decode(token, PUBKEY, algorithms=["RS256"], options={"require": ["exp","iss","sub"]})
    except jwt.PyJWTError as e:
        return jsonify({"error":"invalid token","detail":str(e)}), 401
    # Build compact policy message for constrained devices
    policy_msg = {"sub": claims["sub"], "action":"optout", "ts": claims["iat"]}
    mqttc.publish(MQTT_TOPIC, json.dumps(policy_msg), qos=1)  # reliable local propagation
    audit({"event":"optout","claims":claims})
    return jsonify({"status":"accepted"}), 202

if __name__ == "__main__":
    # Production should run under Gunicorn/uWSGI and with proper file permissions.
    app.run(host="0.0.0.0", port=8443, ssl_context=("/etc/ssl/certs/gw.crt","/etc/ssl/private/gw.key"))