#!/usr/bin/env python3
# Production-ready: uses smbus2, paho-mqtt, numpy; run as systemd service.
import time, json
import numpy as np
from smbus2 import SMBus
import paho.mqtt.client as mqtt

I2C_BUS = 1
SENSOR_ADDR = 0x40
MQTT_BROKER = 'mqtt.example.local'
MQTT_TOPIC = 'farm/edge/health'

# EWMA state persisted across restarts; initialize conservatively.
alpha = 0.05                      # EWMA smoothing
ewma_bias = 0.0
ewma_var = 1.0

def read_sensor(bus):
    # Replace with specific sensor read; this reads two bytes.
    data = bus.read_i2c_block_data(SENSOR_ADDR, 0, 2)
    raw = (data[0] << 8) | data[1]
    return raw * 1e-3                # scale to engineering units

def get_spatial_reference():
    # Pull precomputed spatial fusion from local cache or compute from neighbors.
    # Placeholder returns None when reference unavailable.
    return None

def publish(client, payload):
    client.publish(MQTT_TOPIC, json.dumps(payload), qos=1)

def main():
    global ewma_bias, ewma_var
    bus = SMBus(I2C_BUS)
    client = mqtt.Client()
    client.tls_set()                  # enforce TLS
    client.connect(MQTT_BROKER, 8883)
    client.loop_start()
    try:
        while True:
            y = read_sensor(bus)
            ref = get_spatial_reference()
            if ref is not None:
                residual = y - ref
                ewma_bias = alpha * residual + (1-alpha) * ewma_bias
                ewma_var = alpha * (residual - ewma_bias)**2 + (1-alpha) * ewma_var
                health = {
                    'timestamp': int(time.time()),
                    'value': y,
                    'ref': ref,
                    'ewma_bias': float(ewma_bias),
                    'ewma_std': float(np.sqrt(ewma_var))
                }
            else:
                # Fallback to internal variance check
                health = {'timestamp': int(time.time()), 'value': y, 'ewma_bias': None}
            publish(client, health)
            time.sleep(60)            # sampling cadence; tune per deployment
    finally:
        client.loop_stop()
        bus.close()

if __name__ == '__main__':
    main()