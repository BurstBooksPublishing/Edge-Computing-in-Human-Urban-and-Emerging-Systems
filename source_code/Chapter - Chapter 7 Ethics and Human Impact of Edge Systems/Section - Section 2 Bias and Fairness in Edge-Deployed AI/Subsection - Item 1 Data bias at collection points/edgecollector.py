#!/usr/bin/env python3
"""
Edge collector: maintains per-class reservoir, logs metadata, publishes summaries.
Dependencies: paho-mqtt, numpy. Designed for Raspberry Pi / Jetson.
"""
from dataclasses import dataclass
import time, json, random, logging, threading
import numpy as np
import paho.mqtt.client as mqtt

@dataclass
class Config:
    device_id: str = "edge-001"
    mqtt_broker: str = "broker.local"
    mqtt_topic: str = "edge/summary"
    max_reservoir_per_class: int = 100  # bounded storage
    report_interval_s: int = 60

class EdgeCollector:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.reservoirs = {}           # class -> list of samples (payload refs)
        self.counts = {}               # class -> int
        self.lock = threading.Lock()
        self.client = mqtt.Client(client_id=cfg.device_id)
        self.client.connect(cfg.mqtt_broker)
        self.start_reporter()

    def capture_sample(self, label: str, payload_meta: dict):
        # payload_meta should include timestamp, exposure, device_cal, compress_level
        with self.lock:
            n = self.counts.get(label, 0) + 1
            self.counts[label] = n
            R = self.cfg.max_reservoir_per_class
            bucket = self.reservoirs.setdefault(label, [])
            if len(bucket) < R:
                bucket.append(payload_meta)
            else:
                # reservoir sampling replacement probability
                k = random.randint(1, n)
                if k <= R:
                    idx = random.randrange(R)
                    bucket[idx] = payload_meta

    def start_reporter(self):
        def reporter():
            while True:
                time.sleep(self.cfg.report_interval_s)
                self.publish_summary()
        t = threading.Thread(target=reporter, daemon=True)
        t.start()

    def publish_summary(self):
        with self.lock:
            summary = {
                "device_id": self.cfg.device_id,
                "timestamp": time.time(),
                "counts": self.counts,
                "reservoir_counts": {k: len(v) for k,v in self.reservoirs.items()}
            }
        # lightweight privacy-preserving summary publish
        self.client.publish(self.cfg.mqtt_topic, json.dumps(summary), qos=1)

# usage: detector calls collector.capture_sample(label, metadata)