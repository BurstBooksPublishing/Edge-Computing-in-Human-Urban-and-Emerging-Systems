#!/usr/bin/env python3
# Production-ready adaptive agent for edge gateways.
# Requires: psutil, paho-mqtt, onnxruntime (optional), pynvml (optional).
import time
import json
import psutil
import paho.mqtt.client as mqtt

BROKER = "mqtt.example.local"          # control-plane broker
DEVICE_ID = "edge-gateway-01"
SAMPLE_INTERVAL_MIN = 0.1             # seconds
SAMPLE_INTERVAL_MAX = 1.0
CPU_HIGH = 0.85                        # high utilization threshold
CPU_LOW = 0.60                         # low utilization threshold
MODEL_HEAVY = "detector_resnet.onnx"
MODEL_LIGHT = "detector_mobilenet.onnx"

client = mqtt.Client(client_id=DEVICE_ID)
client.connect(BROKER, 1883, 60)

def publish_policy(policy):
    payload = json.dumps(policy)
    client.publish(f"edge/control/{DEVICE_ID}", payload, qos=1)

def get_gpu_util():
    try:
        import pynvml
        pynvml.nvmlInit()
        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        util = pynvml.nvmlDeviceGetUtilizationRates(h).gpu / 100.0
        pynvml.nvmlShutdown()
        return util
    except Exception:
        return 0.0

def measure_load(window=1.0):
    # average CPU percent and GPU percent over window
    samples = int(max(1, window / 0.1))
    cpu = 0.0
    gpu = 0.0
    for _ in range(samples):
        cpu += psutil.cpu_percent(interval=0.1) / 100.0
        gpu += get_gpu_util()
    return cpu / samples, gpu / samples

def decide_action(cpu_load, gpu_load, current_interval, current_model):
    # simple hysteresis rule: adjust sampling and model selection
    if cpu_load > CPU_HIGH or gpu_load > CPU_HIGH:
        new_interval = min(SAMPLE_INTERVAL_MAX, current_interval * 1.5)
        new_model = MODEL_LIGHT
    elif cpu_load < CPU_LOW and gpu_load < CPU_LOW:
        new_interval = max(SAMPLE_INTERVAL_MIN, current_interval * 0.8)
        new_model = MODEL_HEAVY
    else:
        new_interval = current_interval
        new_model = current_model
    return new_interval, new_model

def main_loop():
    sample_interval = 0.25
    current_model = MODEL_HEAVY
    while True:
        cpu_load, gpu_load = measure_load(window=1.0)
        sample_interval, chosen_model = decide_action(
            cpu_load, gpu_load, sample_interval, current_model)
        policy = {
            "sample_interval": sample_interval,
            "model": chosen_model,
            "cpu": cpu_load, "gpu": gpu_load, "ts": time.time()
        }
        publish_policy(policy)
        current_model = chosen_model
        time.sleep(max(0.01, sample_interval))

if __name__ == "__main__":
    main_loop()