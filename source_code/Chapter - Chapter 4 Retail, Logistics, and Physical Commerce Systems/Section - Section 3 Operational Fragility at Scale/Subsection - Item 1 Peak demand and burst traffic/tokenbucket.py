import asyncio
import time
import psutil             # system metrics on Linux-based edge nodes
import paho.mqtt.client as mqtt

BROKER = "edge-broker.local"
TOPIC = "store/entrance/detections"
RATE = 20.0             # tokens per second (sustained rate)
BURST = 40              # max tokens saved
Q_MAX = 500             # max queue length before shedding
CPU_THRESHOLD = 85.0    # percent

class TokenBucket:
    def __init__(self, rate, burst):
        self.rate = rate
        self.capacity = burst
        self.tokens = burst
        self.last = time.monotonic()
    def consume(self, n=1):
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.last)*self.rate)
        self.last = now
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False

async def publisher(loop, queue):
    client = mqtt.Client()
    client.connect(BROKER)
    tb = TokenBucket(RATE, BURST)
    while True:
        item = await queue.get()
        # shed if queue too long or CPU is high
        if queue.qsize() > Q_MAX or psutil.cpu_percent() > CPU_THRESHOLD:
            # local aggregation or drop strategy
            # here we compress and send a summary to reduce load
            payload = b"summary:" + item[:64]
            client.publish(TOPIC, payload=qos=1)
            queue.task_done()
            continue
        # rate-limited send
        while not tb.consume():
            await asyncio.sleep(0.01)
        client.publish(TOPIC, payload=item, qos=1)
        queue.task_done()

# producer would push detection payloads into the queue