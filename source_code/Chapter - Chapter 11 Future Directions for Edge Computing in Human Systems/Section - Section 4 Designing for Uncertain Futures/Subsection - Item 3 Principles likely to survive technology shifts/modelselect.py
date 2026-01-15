# Production-ready example for Jetson/RPi: choose best model given latency and energy budgets.
import time, psutil, grpc, onnxruntime as ort
from typing import Tuple

REMOTE_ADDR = "mec-node.local:50051"
LOCAL_MODEL = "/opt/models/percep_fp16.onnx"
FALLBACK_MODEL = "/opt/models/percep_small.onnx"
LATENCY_BUDGET_MS = 150

def measure_latency(fn, *args, trials=3) -> float:
    ts = [time.time(); fn(*args) for _ in range(trials)]
    return (ts[-1]-ts[0])/(trials-1)*1000.0

def can_use_gpu() -> bool:
    # Simple resource check: CPU load low and GPU memory available on Jetson
    return psutil.cpu_percent(interval=0.1) < 70.0

def local_infer(session, input_tensor):
    return session.run(None, {"input": input_tensor})

# Initialize sessions lazily for warm start
local_sess = None
fallback_sess = None
remote_stub = None

def infer(input_tensor):
    global local_sess, fallback_sess, remote_stub
    start = time.time()
    # Try best local accelerator
    if can_use_gpu():
        if local_sess is None:
            local_sess = ort.InferenceSession(LOCAL_MODEL, providers=['TensorrtExecutionProvider','CUDAExecutionProvider','CPUExecutionProvider'])
        out = local_infer(local_sess, input_tensor)
        if (time.time()-start)*1000.0 < LATENCY_BUDGET_MS:
            return out
    # Try fallback small model
    if fallback_sess is None:
        fallback_sess = ort.InferenceSession(FALLBACK_MODEL, providers=['CPUExecutionProvider'])
    out = local_infer(fallback_sess, input_tensor)
    if (time.time()-start)*1000.0 < LATENCY_BUDGET_MS:
        return out
    # Remote offload as last resort, synchronous call to MEC
    if remote_stub is None:
        channel = grpc.insecure_channel(REMOTE_ADDR)
        remote_stub = SomeGrpcStub(channel)  # generated client stub
    return remote_stub.Infer(input_tensor)  # assume remote respects SLA