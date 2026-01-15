#!/usr/bin/env python3
# Minimal production-ready module: enforce residency & DP, publish via MQTT
import json, time, math, random, logging
import paho.mqtt.client as mqtt

# Load policy mapping site -> allowed_sinks and epsilon limits
with open('/etc/edge/policy.json') as f:
    POLICY = json.load(f)

# Local aggregation window
WINDOW_SECONDS = 5

def laplace_noise(scale):
    u = random.random() - 0.5
    return -scale * math.copysign(1.0, u) * math.log(1 - 2*abs(u))

def dp_aggregate(values, epsilon, sensitivity=1.0):
    scale = sensitivity / epsilon
    noisy_sum = sum(values) + laplace_noise(scale)
    return noisy_sum

def allowed_to_send(site, sink):
    entry = POLICY.get(site, {})
    return sink in entry.get('allowed_sinks', [])

# MQTT client configured with certificate signed by local CA; private key loaded
# from TPM via PKCS#11 in production (abstracted here).
client = mqtt.Client()
client.tls_set('/etc/edge/ca.crt', certfile='/etc/edge/cert.pem',
               keyfile='/etc/edge/key.pem')  # use PKCS#11/TSS in real deployments
client.connect('broker.local', 8883)

def process_window(site, measurements, task):
    # policy contains epsilon limit per jurisdiction
    epsilon = POLICY.get(site, {}).get('epsilon_max', 0.5)
    # enforce lower bound for numeric stability
    epsilon = max(epsilon, 1e-3)
    agg = dp_aggregate(measurements, epsilon)
    payload = {'site': site, 'task': task, 'value': agg, 'epsilon': epsilon}
    sinks = POLICY.get(site, {}).get('preferred_sinks', ['local'])
    for sink in sinks:
        if allowed_to_send(site, sink):
            topic = f'urban/{sink}/{task}'
            client.publish(topic, json.dumps(payload), qos=1)
        else:
            # store locally; rotate files with systemd-tmpfiles or similar
            with open(f'/var/edge/store/{site}_{task}.json','a') as fh:
                fh.write(json.dumps(payload)+'\n')

# Example loop receiving raw measurements from sensors
def run():
    while True:
        # read sensor buffer aggregated elsewhere (camera counts, LIDAR echoes)
        # here: stubbed sample numbers
        site='site_A_eu'  # POLICY keyed by site identifier; avoid raw underscores in docs
        measurements = [1,0,2,1,1]  # placeholder
        process_window(site, measurements, task='vehicle_count')
        time.sleep(WINDOW_SECONDS)

if __name__=='__main__':
    logging.basicConfig(level=logging.INFO)
    run()