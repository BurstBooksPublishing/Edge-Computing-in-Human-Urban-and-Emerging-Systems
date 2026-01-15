import time, random, json, numpy as np
import paho.mqtt.client as mqtt
# tflite_runtime on Jetson/RPi; fallback to tensorflow.lite on other Linux
from tflite_runtime.interpreter import Interpreter  # edge-friendly runtime

# Load TFLite model for context->score
interp = Interpreter(model_path="context_model.tflite")
interp.allocate_tensors()
input_idx = interp.get_input_details()[0]['index']
output_idx = interp.get_output_details()[0]['index']

MQTT_BROKER="broker.local"
CLIENT_ID="edge_scheduler_01"
TOPIC_TELEMETRY="city/charging/telemetry"

client = mqtt.Client(CLIENT_ID)
client.connect(MQTT_BROKER)

# Configuration: group quotas (minimum exposure fraction)
GROUPS = ["A","B","C"]
min_quota = {"A":0.10,"B":0.20,"C":0.05}  # engineering policy
exposure_counts = {g:1e-6 for g in GROUPS}  # smoothing

epsilon = 0.1  # base exploration
decay = 0.999

def infer_context(ctx_features):
    # ctx_features: numpy array
    interp.set_tensor(input_idx, ctx_features.astype(np.float32))
    interp.invoke()
    return float(interp.get_tensor(output_idx)[0])

def select_action(context, candidate_actions, group_map):
    # candidate_actions: list of actions; group_map: action->group
    scores = [infer_context(np.array([context + a['feat']])) for a in candidate_actions]
    # apply constrained epsilon-greedy: prefer highest score unless it violates quotas
    if random.random() < epsilon:
        return random.choice(candidate_actions)
    # compute expected exposure if choose each action
    best = None
    for a, s in zip(candidate_actions, scores):
        g = group_map[a['id']]
        projected = exposure_counts[g] + 1.0  # naive projection
        # penalize choices that would reduce relative quota
        penalty = max(0.0, (min_quota[g]*sum(exposure_counts.values()) - projected))
        score = s - 1000.0*penalty
        if best is None or score > best[0]:
            best = (score, a, g)
    return best[1]

def record_exposure(group):
    exposure_counts[group] += 1.0

def publish_telemetry(payload):
    client.publish(TOPIC_TELEMETRY, json.dumps(payload))

# Main loop (edge-friendly, non-blocking)
while True:
    # Acquire local sensing (camera/occupancy/canbus) - placeholder
    context = np.random.rand()  # replace with real sensor vector
    candidates = [{"id":"slot1","feat":0.1},{"id":"slot2","feat":0.2}]
    group_map = {"slot1":"A","slot2":"B"}
    action = select_action(context, candidates, group_map)
    # Execute action via local actuator API (system call or RTOS message)
    # ... execute action ...
    record_exposure(group_map[action['id']])
    publish_telemetry({"action":action['id'],"group":group_map[action['id']],"time":time.time()})
    epsilon *= decay
    time.sleep(1.0)  # rate control for edge node