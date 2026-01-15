import json, time, math, random
import paho.mqtt.client as mqtt  # robust MQTT client for edge messaging

STATE_PATH = "/var/lib/edge_adapt/state.json"
MQTT_BROKER = "localhost"
TOPIC_FEEDBACK = "xr/user_feedback"   # explicit ratings and implicit events

# safe bounds for parameters
MIN_SCALE, MAX_SCALE = 0.5, 1.0
MIN_OFFLOAD, MAX_OFFLOAD = 0.0, 1.0

class AdaptiveController:
    def __init__(self):
        self.ema_reward = 0.0
        self.alpha = 0.2               # EMA smoothing
        self.epsilon = 0.1             # exploration probability
        self.current = {"scale": 0.9, "offload": 0.3}
        self._load_state()
        self.client = mqtt.Client()
        self.client.on_message = self._on_msg
        self.client.connect(MQTT_BROKER)
        self.client.subscribe(TOPIC_FEEDBACK)
        self.client.loop_start()

    def _load_state(self):
        try:
            with open(STATE_PATH,"r") as f:
                self.ema_reward, self.current = json.load(f)
        except Exception:
            pass

    def _save_state(self):
        with open(STATE_PATH,"w") as f:
            json.dump([self.ema_reward, self.current], f)

    def _on_msg(self, client, userdata, msg):
        # payload: {"type":"explicit","score":0.8} or {"type":"implicit","blink_rate":3.2}
        data = json.loads(msg.payload.decode())
        r = self._map_feedback_to_reward(data)
        self._update_ema(r)
        self._adapt_parameters()

    def _map_feedback_to_reward(self, data):
        if data.get("type")=="explicit":
            return max(-1.0, min(1.0, float(data.get("score",0.0))))
        # simple implicit mapping: high blink rate -> negative
        if "blink_rate" in data:
            return -0.5 if data["blink_rate"]>4.0 else 0.2
        if "head_jitter" in data:
            return -0.7 if data["head_jitter"]>0.15 else 0.1
        return 0.0

    def _update_ema(self, r):
        self.ema_reward = (1-self.alpha)*self.ema_reward + self.alpha*r
        self._save_state()

    def _adapt_parameters(self):
        # simple epsilon-greedy; prefer lower offload when EMA negative
        if random.random() < self.epsilon:
            # explore small random perturbation
            self.current["scale"] = max(MIN_SCALE, min(MAX_SCALE,
                self.current["scale"] + (random.random()-0.5)*0.1))
        else:
            if self.ema_reward < -0.2:
                self.current["offload"] = max(MIN_OFFLOAD, self.current["offload"]-0.1)
                self.current["scale"] = min(MAX_SCALE, self.current["scale"]+0.05)
            elif self.ema_reward > 0.2:
                self.current["offload"] = min(MAX_OFFLOAD, self.current["offload"]+0.05)
        # publish policy to local render manager
        mqtt.Client().connect(MQTT_BROKER).publish("xr/policy", json.dumps(self.current))