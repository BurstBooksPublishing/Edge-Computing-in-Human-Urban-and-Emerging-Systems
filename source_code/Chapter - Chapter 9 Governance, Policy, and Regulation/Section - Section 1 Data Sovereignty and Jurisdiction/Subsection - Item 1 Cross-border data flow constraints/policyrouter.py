#!/usr/bin/env python3
# Minimal, production-oriented policy router for edge gateways.
# Dependencies: pyyaml, requests, paho-mqtt, certifi, tenacity

import yaml, logging, json, socket
from pathlib import Path
import requests, paho.mqtt.publish as mqtt_publish
from tenacity import retry, stop_after_attempt, wait_exponential

# Load policy: mapping of data_class -> allowed_countries
POLICY_FILE = Path("/etc/edge/policy.yaml")
policy = yaml.safe_load(POLICY_FILE.read_text())

LOCAL_BROKER = {"host":"127.0.0.1","port":1883}
CLOUD_EP = "https://regional-cloud.example/api/ingest"
MTLS_CLIENT_CERT = ("/etc/edge/certs/client.crt", "/etc/edge/certs/client.key")

logger = logging.getLogger("policy_router")
logger.setLevel(logging.INFO)

def classify_event(evt):
    # Minimal classifier: assumes evt has 'country' and 'data_class'
    return evt.get("data_class"), evt.get("country")

@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, max=10))
def send_to_cloud(payload):
    # mTLS enforced, verify server certs using certifi bundle
    resp = requests.post(CLOUD_EP, json=payload,
                         cert=MTLS_CLIENT_CERT, timeout=5, verify=True)
    resp.raise_for_status()
    return resp

def route_event(evt):
    data_class, origin_country = classify_event(evt)
    allowed = policy.get(data_class, [])
    if origin_country in allowed:
        # Local ingestion: publish to local MQTT for durable processing
        mqtt_publish.single("ingest/events", json.dumps(evt), hostname=LOCAL_BROKER["host"],
                            port=LOCAL_BROKER["port"])
        logger.info("Ingested locally: %s", evt.get("id"))
    else:
        # Export: ensure payload is minimized before export
        minimized = {k:evt[k] for k in ("id","hash") if k in evt}
        try:
            send_to_cloud(minimized)
            logger.info("Exported event id=%s to cloud", evt.get("id"))
        except Exception as e:
            logger.error("Export failed: %s; storing locally for audit", e)
            mqtt_publish.single("ingest/blocked_exports", json.dumps(evt),
                                hostname=LOCAL_BROKER["host"], port=LOCAL_BROKER["port"])

# Example event processing loop omitted for brevity (subscribe to local socket or broker).