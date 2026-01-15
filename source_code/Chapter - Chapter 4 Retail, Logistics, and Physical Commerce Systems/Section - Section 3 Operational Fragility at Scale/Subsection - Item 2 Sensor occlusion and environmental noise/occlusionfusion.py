import time, json
import numpy as np
import paho.mqtt.client as mqtt
from filterpy.kalman import KalmanFilter

# Set up MQTT (production: TLS, auth)
client = mqtt.Client()
client.connect("broker.example.com",1883,60)

# Minimal Kalman filter for 2D position
kf = KalmanFilter(dim_x=4, dim_z=2)
kf.F = np.array([[1,0,1,0],[0,1,0,1],[0,0,1,0],[0,0,0,1]])  # motion
kf.H = np.array([[1,0,0,0],[0,1,0,0]])
kf.P *= 1000
kf.R = np.eye(2)*0.5

def compute_occlusion_camera(det_confidence, crowd_mask_score):
    # det_confidence in [0,1], crowd_mask_score in [0,1]
    return max(0.0, min(1.0, 1.0 - det_confidence + 0.8*crowd_mask_score))

def compute_occlusion_rfid(read_rate, rssi_var):
    return max(0.0, min(1.0, 1.0 - read_rate/10.0 + 0.2*rssi_var))

def fuse_and_update(meas_list):
    # meas_list: list of (z, occlusion_prob) tuples
    weights = [1.0 - o for (_, o) in meas_list]
    if sum(weights) < 0.1:
        # low confidence: publish alert and skip heavy compute
        client.publish("edge/alerts", json.dumps({"event":"low_confidence","t":time.time()}))
        return
    # weighted measurement (simple average)
    z = sum(w * m for (m, _), w in zip(meas_list, weights)) / sum(weights)
    kf.predict()
    kf.update(z)
    est = kf.x.copy()
    client.publish("edge/summary", json.dumps({"pos": est[:2].tolist(), "cov": kf.P[:2,:2].tolist()}))

# Example loop (replace with real sensor I/O)
while True:
    cam_z = np.array([1.2, 3.4])
    cam_conf = 0.6
    crowd_score = 0.3
    rfid_z = np.array([1.1, 3.5])
    read_rate = 8.0
    rssi_var = 0.5

    oc_cam = compute_occlusion_camera(cam_conf, crowd_score)
    oc_rfid = compute_occlusion_rfid(read_rate, rssi_var)

    fuse_and_update([(cam_z, oc_cam), (rfid_z, oc_rfid)])
    time.sleep(0.05)