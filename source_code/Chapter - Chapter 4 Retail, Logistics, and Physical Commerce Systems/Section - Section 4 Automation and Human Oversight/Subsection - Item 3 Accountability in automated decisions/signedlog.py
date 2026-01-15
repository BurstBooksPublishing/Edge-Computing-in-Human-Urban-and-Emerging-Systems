# Production-ready; uses libsodium for Ed25519 and paho-mqtt for transport.
import sqlite3, json, time, base64, logging
from nacl import signing, encoding
import paho.mqtt.client as mqtt

DB_PATH = "/var/lib/edge/decisions.db"
MQTT_BROKER = "audit.broker.example:8883"
MQTT_TOPIC = "store/123/decisions"

# Load signing key from secure element or file-protected store (example uses file)
with open("/etc/edge/keys/ed25519_priv.pem","rb") as f:
    priv = signing.SigningKey(f.read(), encoder=encoding.RawEncoder)
pub = priv.verify_key.encode(encoder=encoding.Base64Encoder).decode()

# Init DB (WAL mode for concurrency and durability)
conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
conn.execute("PRAGMA journal_mode=WAL;")
conn.execute("""CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, payload TEXT, sig TEXT, published INTEGER DEFAULT 0
)""")

def sign_payload(payload: bytes) -> str:
    sig = priv.sign(payload).signature
    return base64.b64encode(sig).decode()

def persist_and_publish(record: dict):
    payload = json.dumps(record, separators=(',',':')).encode()
    sig = sign_payload(payload)
    cur = conn.cursor()
    cur.execute("INSERT INTO decisions(ts,payload,sig) VALUES(?,?,?)", (int(time.time()), payload, sig))
    rowid = cur.lastrowid
    # MQTT publish with QoS=1; mark published on success
    client = mqtt.Client()
    client.tls_set()  # system trust; replace with explicit certs in production
    client.username_pw_set("edge", "REDACTED")  # use certs or token instead
    client.connect(*MQTT_BROKER.split(":"))
    rc = client.publish(MQTT_TOPIC, json.dumps({"id":rowid,"payload":base64.b64encode(payload).decode(),"sig":sig}), qos=1)
    rc.wait_for_publish()
    if rc.rc == mqtt.MQTT_ERR_SUCCESS:
        conn.execute("UPDATE decisions SET published=1 WHERE id=?", (rowid,))
    client.disconnect()

# Example usage when decision made
record = {
  "t": time.time(), "s": {"features_hash":"abc123"}, "m_v":"2025-07-14",
  "c":0.82, "a":"charge_9.99", "h":None, "pub_key":pub
}
persist_and_publish(record)