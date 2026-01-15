import json, time
from paho.mqtt import client as mqtt  # pip install paho-mqtt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

# Load private key from secure module or protected file (illustrative).
with open('/etc/edge/device_priv.pem', 'rb') as f:
    priv = serialization.load_pem_private_key(f.read(), password=None, backend=default_backend())

def sign(record: dict) -> str:
    payload = json.dumps(record, separators=(',', ':'), sort_keys=True).encode()
    sig = priv.sign(payload, padding.PKCS1v15(), hashes.SHA256())
    return sig.hex()

mqttc = mqtt.Client(client_id='device-123')          # device identity
mqttc.tls_set(ca_certs='/etc/edge/ca.pem',
              certfile='/etc/edge/device_cert.pem',
              keyfile='/etc/edge/device_key.pem')    # mTLS
mqttc.connect('mqtt-broker.example.com', 8883, 60)

record = {'ts': int(time.time()), 'event': 'binary_mismatch', 'hash': '...'}
record['signature'] = sign(record)
mqttc.publish('audit/device-123', json.dumps(record), qos=1)
mqttc.disconnect()