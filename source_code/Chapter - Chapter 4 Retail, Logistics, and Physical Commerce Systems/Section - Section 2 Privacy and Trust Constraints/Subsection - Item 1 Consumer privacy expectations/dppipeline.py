import numpy as np
import paho.mqtt.client as mqtt
from tflite_runtime.interpreter import Interpreter  # tiny runtime for edge

# init interpreter (quantized model deployed as model.tflite)
interpreter = Interpreter(model_path="model.tflite")
interpreter.allocate_tensors()
input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

# MQTT client (TLS certs handled by environment)
client = mqtt.Client()
client.tls_set()  # use system certs; device key in secure element
client.connect("aggregator.example.local", 8883)

def laplace_noise(scale):
    return np.random.laplace(0.0, scale)

def infer_and_publish(frame, epsilon):
    # preprocess frame to model input (resize, normalize) -- fast ops only
    inp = preprocess_frame(frame)                         # implement efficiently
    interpreter.set_tensor(input_details[0]['index'], inp)
    interpreter.invoke()
    detections = interpreter.get_tensor(output_details[0]['index'])
    count = postprocess_count(detections)                 # count persons detected

    # apply Laplace DP for count queries (sensitivity = 1)
    scale = 1.0 / float(epsilon)
    noisy_count = float(count) + float(laplace_noise(scale))

    payload = {"ts": int(time.time()), "noisy_count": noisy_count}
    client.publish("store1/entrance/count", json.dumps(payload), qos=1)

# runtime loop (simplified)
while True:
    frame = camera.read()
    infer_and_publish(frame, epsilon=0.5)  # epsilon set per policy