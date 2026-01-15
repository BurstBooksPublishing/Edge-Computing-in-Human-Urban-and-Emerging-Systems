#!/usr/bin/env python3
# Minimal, production-minded code: use proper key storage and restart supervision.
import sqlite3, hashlib, time, json, requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

DB_PATH = "/var/lib/edge_audit/audit.db"
PUBLISH_URL = "https://transparency.city.example/api/v1/roots"  # FIWARE NGSI-LD or OpenAPI
EPOCH_SEC = 60

# Use a hardware-backed key; here we load a PEM for clarity.
with open("/etc/edge_audit/ecdsa_priv.pem","rb") as f:
    priv = serialization.load_pem_private_key(f.read(), password=None)

def init_db():
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("CREATE TABLE IF NOT EXISTS entries(id INTEGER PRIMARY KEY, ts INTEGER, payload JSON, sig BLOB);")
    return conn

def sign_entry(payload_b):
    digest = hashlib.sha256(payload_b).digest()
    sig = priv.sign(digest, ec.ECDSA(hashes.SHA256()))
    return sig

def append_entry(conn, payload):
    payload_b = json.dumps(payload, separators=(",",":")).encode()
    sig = sign_entry(payload_b)
    conn.execute("INSERT INTO entries(ts,payload,sig) VALUES(?,?,?)", (int(time.time()), payload_b, sig))

def fetch_epoch(conn, since_id=0):
    cur = conn.execute("SELECT id,payload FROM entries WHERE id>? ORDER BY id", (since_id,))
    return cur.fetchall()

def merkle_root(hashes):
    # simple binary tree; production: use optimized library
    while len(hashes) > 1:
        pairs = []
        for i in range(0, len(hashes), 2):
            a = hashes[i]
            b = hashes[i+1] if i+1 < len(hashes) else a
            pairs.append(hashlib.sha256(a+b).digest())
        hashes = pairs
    return hashes[0] if hashes else hashlib.sha256(b'').digest()

def publish_root(root_b, epoch_ts):
    payload = {"root": root_b.hex(), "ts": epoch_ts}
    # TLS, mutual auth, retries, and JSON schema validation required in production.
    r = requests.post(PUBLISH_URL, json=payload, timeout=5)
    r.raise_for_status()

def main_loop():
    conn = init_db()
    last_id = 0
    while True:
        time.sleep(EPOCH_SEC)
        rows = fetch_epoch(conn, since_id=last_id)
        if not rows:
            continue
        last_id = rows[-1][0]
        hashes = [hashlib.sha256(row[1]).digest() for row in rows]
        root = merkle_root(hashes)
        # sign root with device key and publish
        publish_root(root, int(time.time()))

if __name__ == "__main__":
    main_loop()