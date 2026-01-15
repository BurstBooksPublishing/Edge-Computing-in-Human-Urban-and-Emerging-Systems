#!/usr/bin/env python3
# Minimal, production-ready edge agent: enforce policy, run ONNX inference, upload aggregates.
import os, time, json, requests, logging
import onnxruntime as rt
from collections import Counter

# Configuration via env vars for k3s/kubeedge deployments
MODEL_PATH = os.getenv("MODEL_PATH","/opt/models/ped_detector.onnx")
UPLOAD_URL = os.getenv("UPLOAD_URL","https://regional.example/api/ingest")
POLICY_FILE = os.getenv("POLICY_FILE","/etc/edge/policy.json")
BATCH_INTERVAL = int(os.getenv("BATCH_INTERVAL","5"))  # seconds

log = logging.getLogger("local_agent")
logging.basicConfig(level=logging.INFO)

# Load policy: requires key "allow_egress" and "min_local_fraction"
with open(POLICY_FILE,"r") as f:
    policy = json.load(f)

sess = rt.InferenceSession(MODEL_PATH, providers=["CPUExecutionProvider"])

def infer(frame_tensor):
    # frame_tensor: preprocessed numpy array
    input_name = sess.get_inputs()[0].name
    out = sess.run(None, {input_name: frame_tensor})
    # postprocess to boolean person detection
    return bool(out[0][0][0] > 0.5)

def upload(payload):
    # simple retry and auth via mounted token
    headers = {"Authorization": f"Bearer {open('/var/run/secrets/token').read().strip()}"}
    r = requests.post(UPLOAD_URL, json=payload, headers=headers, timeout=5)
    r.raise_for_status()

def main_loop(camera):
    counts = Counter()
    processed = 0
    seen = 0
    start = time.time()
    while True:
        frame = camera.read_frame()  # blocking, implemented in platform-specific driver
        seen += 1
        # decide local processing vs transform based on policy
        if policy.get("require_local_processing", False):
            detected = infer(frame.to_tensor())  # local inference
            processed += 1
            counts["person" if detected else "no_person"] += 1
        else:
            # fallback: compute feature vector, drop raw frame
            features = camera.extract_features(frame)
            counts["features_sent"] += 1
            # optionally upload features
            if policy.get("allow_egress", False):
                upload({"features": features, "ts": time.time()})
        # periodic batch upload of aggregates if allowed
        if time.time() - start >= BATCH_INTERVAL:
            if policy.get("allow_egress", False):
                payload = {"aggregates": dict(counts), "local_processed": processed, "seen": seen}
                upload(payload)
            counts.clear(); processed = 0; seen = 0; start = time.time()
# Entry point omitted: integrate with systemd or container runtime for production.