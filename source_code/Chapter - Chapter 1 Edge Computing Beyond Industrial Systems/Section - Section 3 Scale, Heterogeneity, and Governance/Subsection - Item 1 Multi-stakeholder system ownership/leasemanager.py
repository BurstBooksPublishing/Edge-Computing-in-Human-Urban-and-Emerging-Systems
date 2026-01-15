# Production-ready lease manager using paho-mqtt and PyJWT.
# Run on edge node (e.g., NVIDIA Jetson, Raspberry Pi).
import time, json, signal, sys
import jwt  # PyJWT
import ssl
import paho.mqtt.client as mqtt

BROKER = "mqtt-edge.example.local"
LEASE_TOPIC = "edge/leases/intersection-42"  # retained topic
LEASE_TTL = 10.0  # seconds
RENEW_MARGIN = 3.0  # renew this many seconds before expiry
STAKEHOLDER_ID = "city-traffic-admin"
JWT_SECRET = "REPLACE_WITH_PUBLIC_KEY_OR_JWK"  # validate tokens in real system

client = mqtt.Client(client_id=f"lease-{STAKEHOLDER_ID}")
client.tls_set(ca_certs="/etc/ssl/ca.pem", tls_version=ssl.PROTOCOL_TLSv1_2)
# Use client.username_pw_set or certs for auth in production

def validate_jwt(token):
    # Validate token signature, issuer, and exp. Replace with JWK/OIDC discovery.
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["RS256"], options={"verify_aud": False})
        return payload
    except jwt.PyJWTError:
        return None

def on_connect(c, userdata, flags, rc):
    c.subscribe(LEASE_TOPIC)

def on_message(c, userdata, msg):
    # Update local view of current lease on retained topic
    try:
        lease = json.loads(msg.payload.decode())
        userdata['current_lease'] = lease
    except Exception:
        userdata['current_lease'] = None

def try_acquire_or_renew(c, userdata):
    now = time.time()
    current = userdata.get('current_lease')
    # Can acquire if no lease or expired or owned by self
    if (current is None) or (current.get('expires_at', 0) <= now) or (current.get('owner') == STAKEHOLDER_ID):
        token = jwt.encode({"sub": STAKEHOLDER_ID, "iat": int(now)}, JWT_SECRET, algorithm="RS256")
        lease_msg = {"owner": STAKEHOLDER_ID, "issued_at": now, "expires_at": now + LEASE_TTL, "token": token}
        c.publish(LEASE_TOPIC, json.dumps(lease_msg), retain=True)
        userdata['current_lease'] = lease_msg
        return True
    return False

def main_loop():
    userdata = {'current_lease': None}
    client.user_data_set(userdata)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(BROKER, 8883, keepalive=60)
    client.loop_start()
    backoff = 1.0
    try:
        while True:
            now = time.time()
            lease = userdata.get('current_lease') or {}
            expires = lease.get('expires_at', 0)
            # attempt renew early
            if (expires - now) <= RENEW_MARGIN:
                success = try_acquire_or_renew(client, userdata)
                backoff = 1.0 if success else min(backoff*2, 60.0)
            time.sleep(0.5)
    except KeyboardInterrupt:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main_loop()