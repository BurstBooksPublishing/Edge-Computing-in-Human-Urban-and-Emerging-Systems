#!/usr/bin/env python3
import time, json
import cv2
import numpy as np
import paho.mqtt.client as mqtt
from tflite_runtime.interpreter import Interpreter  # lightweight runtime

MODEL_PATH = "/opt/models/person_detector.tflite"
MQTT_BROKER = "192.0.2.10"
MQTT_TOPIC = "store/entrance/count"
CAM_INDEX = 0
CONF_THRESH = 0.5

# simple centroid tracker state
next_id = 0
tracks = {}

def load_interpreter(path):
    interp = Interpreter(model_path=path, num_threads=2)
    interp.allocate_tensors()
    return interp

def detect(interp, frame):
    inp_details = interp.get_input_details()[0]
    h,w = inp_details['shape'][1:3]
    img = cv2.resize(frame, (w,h))
    img = np.expand_dims(img.astype(np.float32)/255.0, axis=0)
    interp.set_tensor(inp_details['index'], img)
    interp.invoke()
    out = interp.get_tensor(interp.get_output_details()[0]['index'])
    # out assumed N x 6 boxes: [ymin,xmin,ymax,xmax,score,class]
    detections = []
    for d in out[0]:
        score = float(d[4])
        if score < CONF_THRESH: continue
        ymin,xmin,ymax,xmax = map(float, d[0:4])
        detections.append((xmin,ymin,xmax,ymax,score))
    return detections

def update_tracks(detections, frame_shape):
    global next_id, tracks
    centers = []
    for (xmin,ymin,xmax,ymax,_) in detections:
        fx = int((xmin + xmax)/2 * frame_shape[1])
        fy = int((ymin + ymax)/2 * frame_shape[0])
        centers.append((fx,fy))
    # greedy association by distance
    assigned = set()
    new_tracks = {}
    for tid,(cx,cy,last,age) in list(tracks.items()):
        best = None; bestd = 1e9
        for i,c in enumerate(centers):
            if i in assigned: continue
            d = (cx-c[0])**2 + (cy-c[1])**2
            if d < bestd:
                bestd,i = d,i
                best = c
        if best and bestd < 400**2:  # distance threshold
            new_tracks[tid] = (best[0],best[1],time.time(),0)
            assigned.add(i)
        else:
            if age < 5:
                new_tracks[tid] = (cx,cy,last,age+1)
    # add unassigned detections
    for i,c in enumerate(centers):
        if i in assigned: continue
        new_tracks[next_id] = (c[0],c[1],time.time(),0); next_id+=1
    tracks = new_tracks
    return len(tracks)

def mqtt_connect():
    client = mqtt.Client()
    client.tls_set()  # default system CA
    client.connect(MQTT_BROKER, 8883, 60)
    client.loop_start()
    return client

def main():
    interp = load_interpreter(MODEL_PATH)
    cap = cv2.VideoCapture(CAM_INDEX)
    mqttc = mqtt_connect()
    try:
        while True:
            ret,frame = cap.read()
            if not ret: break
            dets = detect(interp, frame)
            count = update_tracks(dets, frame.shape)
            payload = json.dumps({"ts": time.time(), "count": count})
            mqttc.publish(MQTT_TOPIC, payload, qos=1)
            time.sleep(0.05)  # rate limit for CPU budget
    finally:
        cap.release()
        mqttc.loop_stop()
        mqttc.disconnect()

if __name__ == "__main__":
    main()