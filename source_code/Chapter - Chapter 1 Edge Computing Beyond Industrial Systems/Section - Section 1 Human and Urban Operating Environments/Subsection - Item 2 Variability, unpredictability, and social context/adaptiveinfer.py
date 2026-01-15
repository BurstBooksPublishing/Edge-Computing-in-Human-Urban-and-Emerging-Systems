# production-ready adaptive inference loop using tflite runtime and OpenCV
import time, logging
import numpy as np
import cv2
from tflite_runtime.interpreter import Interpreter, load_delegate

MODEL_PATH = "person_detector_edgetpu.tflite"
CAM_INDEX = 0
FPS_MIN, FPS_MAX = 1.0, 15.0
ALPHA = 0.2  # EMA smoothing for arrival rate
THRESH = 0.5

interpreter = Interpreter(model_path=MODEL_PATH,
                          experimental_delegates=[load_delegate('libedgetpu.so')])
interpreter.allocate_tensors()
input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

cap = cv2.VideoCapture(CAM_INDEX)
if not cap.isOpened():
    raise SystemExit("Camera open failed")

ema_lambda = 0.1
last_time = time.time()

try:
    while True:
        start = time.time()
        ret, frame = cap.read()
        if not ret:
            break
        inp = cv2.resize(frame, (input_details[0]['shape'][2],
                                 input_details[0]['shape'][1]))
        inp = np.expand_dims(inp.astype(np.uint8), axis=0)
        interpreter.set_tensor(input_details[0]['index'], inp)
        interpreter.invoke()
        out = interpreter.get_tensor(output_details[0]['index'])
        detections = out[0]

        arrivals = float(np.sum(detections[:,2] > THRESH))
        interval = max(1e-3, time.time() - last_time)
        inst_rate = arrivals / interval
        ema_lambda = ALPHA * inst_rate + (1 - ALPHA) * ema_lambda
        last_time = time.time()

        target_fps = max(FPS_MIN, min(FPS_MAX, FPS_MAX * (ema_lambda / (ema_lambda + 1))))
        sleep_time = max(0, (1.0/target_fps) - (time.time() - start))
        time.sleep(sleep_time)
except KeyboardInterrupt:
    pass
finally:
    cap.release()