import time, json, ssl
import numpy as np
import paho.mqtt.client as mqtt
import onnxruntime as ort

# init deterministic inference session using CUDA/TensorRT where available
sess = ort.InferenceSession("model.onnx", providers=["CUDAExecutionProvider","CPUExecutionProvider"])
input_name = sess.get_inputs()[0].name

# MQTT client with TLS (production TLS certs assumed)
client = mqtt.Client()
client.tls_set(ca_certs="ca.pem", certfile="client.crt", keyfile="client.key", tls_version=ssl.PROTOCOL_TLSv1_2)
client.connect("broker.city.example", 8883, keepalive=60)

def deterministic_integrated_gradients(x, baseline, m=8):
    # fixed small m controls deterministic compute and latency
    alphas = np.linspace(0.0, 1.0, m+1)[1:]
    total_grad = np.zeros_like(x, dtype=np.float32)
    for a in alphas:
        x_step = baseline + a * (x - baseline)
        # single forward with gradient approximation via finite differences
        eps = 1e-3
        grad = (sess.run(None, {input_name: x_step + eps})[0] - sess.run(None, {input_name: x_step - eps})[0]) / (2*eps)
        total_grad += grad
    ig = (x - baseline) * total_grad / m
    return ig.sum(axis=tuple(range(1, ig.ndim)))  # collapse spatial dims for summary

def process_frame(frame):
    start = time.perf_counter()
    # preproc omitted; assume frame -> model_input
    model_input = frame.astype(np.float32)[None, ...]
    pred = sess.run(None, {input_name: model_input})[0]
    infer_t = (time.perf_counter() - start)
    # lightweight explainer using zero baseline
    expl_start = time.perf_counter()
    explanation = deterministic_integrated_gradients(model_input, np.zeros_like(model_input), m=8)
    expl_t = (time.perf_counter() - expl_start)
    total_t = time.perf_counter() - start
    # publish concise explanation and latency metrics
    payload = json.dumps({"pred": int(np.argmax(pred)), "explanation": float(explanation), "t_infer": infer_t, "t_expl": expl_t, "t_total": total_t})
    client.publish("city/intersection/explain", payload, qos=1)
    return payload

# main loop omitted; invoked within RT-scheduled process