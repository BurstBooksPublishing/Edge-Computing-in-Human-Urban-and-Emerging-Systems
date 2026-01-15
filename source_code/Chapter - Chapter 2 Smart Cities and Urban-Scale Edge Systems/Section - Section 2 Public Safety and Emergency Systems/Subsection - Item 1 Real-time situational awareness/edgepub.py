import asyncio
import json
import paho.mqtt.client as mqtt
# Production: secure TLS, client certs, and persistent session required.

MQTT_BROKER = "mqtt.edge.local"            # local broker on gateway
ALERT_TOPIC = "city/alerts/prioritized"    # use namespace without raw underscores in prose

def fuse_scores(sensor_scores, priors):
    # simple log-likelihood accumulation for constrained node
    total = 0.0
    for s, w in zip(sensor_scores, priors):
        total += w * s
    return total

async def run_inference(queue):
    # placeholder: call TensorRT runtime in production for camera frames
    while True:
        frame = await queue.get()
        score = 0.85  # inference result from accelerator
        queue.task_done()
        yield score

def publish_alert(client, alert):
    # publish with QoS=2 for reliable delivery to dispatch systems
    client.publish(ALERT_TOPIC, json.dumps(alert), qos=2, retain=False)

async def main():
    sensor_queue = asyncio.Queue()
    client = mqtt.Client()                     # in production configure TLS and auth
    client.connect(MQTT_BROKER, 1883, 60)
    client.loop_start()
    priors = [1.0, 0.8]                        # weights for audio and vision

    # coroutine that simulates fused decision loop
    async for vision_score in run_inference(sensor_queue):
        audio_score = 0.6                      # aggregated audio posterior
        fused = fuse_scores([audio_score, vision_score], priors)
        if fused > 1.2:                        # threshold tuned offline
            alert = {"ts": int(1000*asyncio.get_event_loop().time()),
                     "score": fused, "type": "gunshot"}
            publish_alert(client, alert)
        await asyncio.sleep(0.005)             # yield to event loop

if __name__ == "__main__":
    asyncio.run(main())