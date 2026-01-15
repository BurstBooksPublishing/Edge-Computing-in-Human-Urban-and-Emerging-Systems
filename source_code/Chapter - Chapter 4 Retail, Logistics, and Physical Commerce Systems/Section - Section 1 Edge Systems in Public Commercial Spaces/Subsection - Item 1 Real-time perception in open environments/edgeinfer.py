import cv2, time, asyncio, paho.mqtt.client as mqtt
import onnxruntime as ort
import numpy as np

# Initialize ONNX Runtime with CUDA provider for GPU inference.
sess = ort.InferenceSession("person_mobilenet_ssd.onnx",
                            providers=['CUDAExecutionProvider','CPUExecutionProvider'])
input_name = sess.get_inputs()[0].name

# MQTT telemetry (TLS certs and auth configured in production).
mqttc = mqtt.Client()
mqttc.tls_set()  # use device provisioned certs
mqttc.username_pw_set("edge-node-id", password="secure-token")
mqttc.connect("broker.local", 8883)

# GStreamer RTSP pipeline tuned for low latency on Jetson.
rtsp_src = ("rtspsrc location=rtsp://camera/stream latency=50 ! "
            "rtph264depay ! h264parse ! omxh264dec ! nvvidconv ! "
            "video/x-raw,format=BGRx ! videoconvert ! appsink")

cap = cv2.VideoCapture(rtsp_src, cv2.CAP_GSTREAMER)

async def preprocess(frame):
    # Resize, normalize, and add batch dim. Use vectorized ops.
    img = cv2.resize(frame, (300,300))
    img = img[:, :, ::-1].astype(np.float32)  # BGR->RGB
    img = (img / 127.5) - 1.0
    return np.expand_dims(np.transpose(img, (2,0,1)), 0)

async def infer_loop():
    last_pub = time.time()
    while True:
        ret, frame = cap.read()
        if not ret:
            await asyncio.sleep(0.01); continue
        inp = await preprocess(frame)  # non-blocking placeholder
        # Synchronous low-latency inference call (fast path).
        outs = sess.run(None, {input_name: inp})
        # Simple postprocess: extract boxes and scores (model-specific).
        boxes, scores, labels = outs[0], outs[1], outs[2]
        count = int((scores > 0.5).sum())
        # Publish every 0.5 s to avoid network spikes.
        if time.time() - last_pub > 0.5:
            mqttc.publish("store/entrance/count", payload=str(count), qos=1)
            last_pub = time.time()
        await asyncio.sleep(0)  # yield to event loop

# Run.
asyncio.run(infer_loop())