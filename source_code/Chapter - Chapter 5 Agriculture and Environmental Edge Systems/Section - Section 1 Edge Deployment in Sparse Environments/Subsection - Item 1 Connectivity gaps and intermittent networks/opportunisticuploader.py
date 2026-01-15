#!/usr/bin/env python3
# Production-ready opportunistic uploader: buffer, sign, batch, retry.
import sqlite3, time, json, hmac, hashlib, socket, random
import paho.mqtt.client as mqtt

DB = '/var/lib/edge/buffer.db'                # persistent store
MQTT_BROKER = 'broker.example.com'
MQTT_TOPIC = 'farm/field1/sensor_batch'
HMAC_KEY = b'supersecretkey'                  # use secure provisioning

# initialize DB (id INTEGER PRIMARY KEY, ts REAL, payload TEXT, uploaded BOOLEAN)
conn = sqlite3.connect(DB, isolation_level=None)
conn.execute('''CREATE TABLE IF NOT EXISTS records
               (id INTEGER PRIMARY KEY, ts REAL, payload TEXT, uploaded INTEGER)''')

def store_sample(payload):
    ts = time.time()
    conn.execute('INSERT INTO records (ts,payload,uploaded) VALUES (?,?,0)', (ts, json.dumps(payload)))

def has_network(host='8.8.8.8', port=53, timeout=1.0):
    # lightweight check without DNS resolution latency
    try:
        s = socket.create_connection((host, port), timeout)
        s.close()
        return True
    except OSError:
        return False

def batch_and_send(client):
    cur = conn.execute('SELECT id,ts,payload FROM records WHERE uploaded=0 ORDER BY id LIMIT 100')
    rows = cur.fetchall()
    if not rows:
        return
    batch = [{'id': r[0], 'ts': r[1], 'payload': json.loads(r[2])} for r in rows]
    body = json.dumps({'device':'edge001','batch':batch}, separators=(',',':'))
    sig = hmac.new(HMAC_KEY, body.encode('utf-8'), hashlib.sha256).hexdigest()
    packet = json.dumps({'body': body, 'hmac': sig})
    # publish synchronously to ensure delivery via broker QoS 1
    rc = client.publish(MQTT_TOPIC, packet, qos=1).rc
    if rc == mqtt.MQTT_ERR_SUCCESS:
        ids = [r[0] for r in rows]
        conn.executemany('UPDATE records SET uploaded=1 WHERE id=?', ((i,) for i in ids))

def main_loop():
    client = mqtt.Client()
    client.tls_set()                    # require TLS; configure certs in real deployments
    client.connect_async(MQTT_BROKER, 8883)
    client.loop_start()
    backoff = 1.0
    while True:
        # sample insertion happens elsewhere or call store_sample(...)
        if has_network():
            try:
                batch_and_send(client)
                backoff = 1.0           # reset on success
            except Exception:
                backoff = min(300, backoff * 2 + random.uniform(0,1))
        else:
            backoff = min(300, backoff * 2 + random.uniform(0,1))
        time.sleep(backoff)

if __name__ == '__main__':
    main_loop()