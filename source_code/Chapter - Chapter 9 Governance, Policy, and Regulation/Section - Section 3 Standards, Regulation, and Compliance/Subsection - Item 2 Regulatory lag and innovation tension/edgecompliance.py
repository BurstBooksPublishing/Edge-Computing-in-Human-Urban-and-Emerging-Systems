#!/usr/bin/env python3
# minimal, production-ready agent skeleton; expand for your CI/CD and TPM integration
import json, subprocess, time, ssl
import paho.mqtt.client as mqtt

BROKER = "mqtt.citybroker.example"
TOPIC = "edge/compliance/report"
CHECK_INTERVAL = 60  # seconds

def get_manifest():
    # gather image and package versions; extend to call your SBOM generator
    out = subprocess.check_output(["/usr/bin/dpkg-query","-W","-f","${Package} ${Version}\n"])
    return {"packages": out.decode().splitlines(), "timestamp": int(time.time())}

def sign_manifest(manifest_json):
    # placeholder: call TPM signing or use private key in secure keystore
    proc = subprocess.Popen(["/usr/bin/openssl","dgst","-sha256","-sign","/etc/keys/edge_priv.pem"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    sig, _ = proc.communicate(input=manifest_json.encode())
    return sig.hex()

def enforce_quarantine(enable):
    # network-level enforcement; use nftables/iptables per platform policies
    if enable:
        subprocess.call(["/sbin/iptables","-A","OUTPUT","-m","owner","--uid-owner","edgeagent","-j","REJECT"])
    else:
        subprocess.call(["/sbin/iptables","-D","OUTPUT","-m","owner","--uid-owner","edgeagent","-j","REJECT"])

def publish(manifest, signature):
    payload = json.dumps({"manifest": manifest, "signature": signature})
    client = mqtt.Client()
    client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
    client.connect(BROKER, 8883)
    client.publish(TOPIC, payload, qos=1)
    client.disconnect()

if __name__ == "__main__":
    while True:
        manifest = get_manifest()
        manifest_json = json.dumps(manifest, sort_keys=True)
        sig = sign_manifest(manifest_json)
        # trivial local policy: quarantine if unsigned packages found (example condition)
        noncompliant = any("untrusted" in p for p in manifest["packages"])
        enforce_quarantine(noncompliant)
        publish(manifest, sig)
        time.sleep(CHECK_INTERVAL)