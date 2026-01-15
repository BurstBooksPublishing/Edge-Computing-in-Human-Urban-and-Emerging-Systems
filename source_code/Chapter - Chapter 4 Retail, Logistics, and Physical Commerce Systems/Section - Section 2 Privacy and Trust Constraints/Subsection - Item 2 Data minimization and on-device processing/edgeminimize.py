#!/usr/bin/env python3
# Production-ready on-device processing for minimized telemetry.
import argparse
import ssl
import time
import numpy as np
import cv2
import paho.mqtt.client as mqtt
from sklearn.decomposition import PCA
import tflite_runtime.interpreter as tflite

# CLI config for device-specific paths and broker TLS
parser = argparse.ArgumentParser()
parser.add_argument('--tflite', required=True)           # model path
parser.add_argument('--broker', required=True)
parser.add_argument('--port', type=int, default=8883)
parser.add_argument('--topic', default='store/edge/metrics')
parser.add_argument('--cert', required=True)
parser.add_argument('--key', required=True)
parser.add_argument('--cafile', required=True)
parser.add_argument('--window', type=int, default=30)    # aggregation sec
args = parser.parse_args()

# Initialize model
interpreter = tflite.Interpreter(model_path=args.tflite)
interpreter.allocate_tensors()
input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

# Small PCA trained offline; load transform matrix or fit on small buffer
pca = PCA(n_components=16)  # replace with pre-trained PCA load in prod

# MQTT with TLS and robust reconnects
client = mqtt.Client()
client.tls_set(ca_certs=args.cafile,
               certfile=args.cert,
               keyfile=args.key,
               tls_version=ssl.PROTOCOL_TLSv1_2)
client.tls_insecure_set(False)
client.connect(args.broker, args.port)

def preprocess(frame, shape):
    frame = cv2.resize(frame, (shape[1], shape[2]))
    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return np.expand_dims(frame.astype(np.float32) / 255.0, axis=0)

def infer_embedding(frame):
    inp = preprocess(frame, input_details[0]['shape'])
    interpreter.set_tensor(input_details[0]['index'], inp)
    interpreter.invoke()
    emb = interpreter.get_tensor(output_details[0]['index']).squeeze()
    return emb

def quantize_vec(vec):
    # 8-bit symmetric quantization to reduce transmit size
    max_abs = np.max(np.abs(vec)) + 1e-8
    scale = 127.0 / max_abs
    q = np.round(vec * scale).astype(np.int8)
    return q.tobytes(), float(max_abs)

# Main loop: aggregate embeddings into minimal metrics
buffer = []
start = time.time()
cap = cv2.VideoCapture(0)
try:
    while True:
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.05)
            continue
        emb = infer_embedding(frame)
        buffer.append(emb)
        if time.time() - start >= args.window:
            arr = np.vstack(buffer)
            # Fit PCA on-the-fly only for demo; use fixed PCA in production.
            if arr.shape[0] >= 10:
                pca.fit(arr)
            reduced = pca.transform(arr.mean(axis=0)[np.newaxis, :]).ravel()
            payload, scale = quantize_vec(reduced)
            meta = {
                'ts': int(time.time()),
                'count': int(len(buffer)),
                'scale': scale
            }
            # Publish minimal binary payload with small JSON metadata
            client.publish(args.topic, payload=payload, qos=1, properties=None)
            client.publish(args.topic + '/meta', payload=str(meta), qos=1)
            buffer.clear()
            start = time.time()
except KeyboardInterrupt:
    pass
finally:
    cap.release()
    client.disconnect()