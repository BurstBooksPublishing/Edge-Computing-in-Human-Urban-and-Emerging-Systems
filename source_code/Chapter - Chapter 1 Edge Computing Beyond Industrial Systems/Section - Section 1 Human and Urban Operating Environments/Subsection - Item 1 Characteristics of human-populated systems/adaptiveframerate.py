#!/usr/bin/env python3
# Production-ready adaptive sampling: on-device inference + MQTT control
import asyncio, time, signal, json
import paho.mqtt.client as mqtt
from datetime import datetime
from inference import PersonDetector  # optimized ONNX/TensorRT wrapper

BROKER='mqtt.example.local'
TOPIC_STATE='edge/node/occupancy'
CAM_DEVICE='/dev/video0'
MIN_FPS=1
MAX_FPS=15
CPU_TEMP_THRESHOLD=80.0  # C

detector = PersonDetector(model_path='/opt/models/person.onnx')
client = mqtt.Client()

async def capture_and_infer(fps):
    # camera capture backend; use v4l2 or gstreamer in production
    frame_interval = 1.0 / fps
    while True:
        ts = time.time()
        frame = await get_frame_async(CAM_DEVICE)  # non-blocking camera API
        count = detector.detect_count(frame)
        payload = {'ts': datetime.utcnow().isoformat(), 'count': count}
        client.publish(TOPIC_STATE, json.dumps(payload), qos=1)
        # adjust sleep to maintain target fps
        await asyncio.sleep(max(0, frame_interval - (time.time() - ts)))

def cpu_temp_celsius():
    # portable read for Linux sysfs; handle missing files gracefully
    try:
        with open('/sys/class/thermal/thermal_zone0/temp') as f:
            return int(f.read().strip()) / 1000.0
    except Exception:
        return 50.0  # conservative default

async def controller():
    # simple controller: increase fps on occupancy, decrease on idle or thermal high
    fps = MIN_FPS
    task = asyncio.create_task(capture_and_infer(fps))
    try:
        while True:
            # occupancy trending: subscribe or infer locally (here local poll)
            recent = await detector.recent_count_avg()  # exp moving avg
            temp = cpu_temp_celsius()
            if temp > CPU_TEMP_THRESHOLD:
                fps = MIN_FPS
            elif recent >= 3:
                fps = min(MAX_FPS, fps + 2)
            elif recent == 0:
                fps = max(MIN_FPS, fps - 1)
            # restart capture task if fps changed
            task.cancel()
            task = asyncio.create_task(capture_and_infer(fps))
            await asyncio.sleep(2.0)
    finally:
        task.cancel()

def main():
    client.connect(BROKER)
    client.loop_start()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, loop.stop)
    loop.run_until_complete(controller())
    client.loop_stop()

if __name__ == '__main__':
    main()