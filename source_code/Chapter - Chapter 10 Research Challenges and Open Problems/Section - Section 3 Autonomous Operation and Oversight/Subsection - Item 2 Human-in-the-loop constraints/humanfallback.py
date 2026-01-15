#!/usr/bin/env python3
# Production-ready ROS2 node managing human-in-the-loop fallback.
import threading
import json
import time
import requests  # small blocking HTTP for signaling (replaceable with aiohttp)
import rclpy
from rclpy.node import Node
from std_msgs.msg import Float32, Bool
from geometry_msgs.msg import Twist

OPERATOR_ENDPOINT = "https://ops.example.com/api/prompt"  # secure endpoint
OPERATOR_TIMEOUT = 5.0  # seconds allowed for human to respond
CONFIDENCE_THRESHOLD = 0.6
TTC_THRESHOLD = 2.5  # seconds

class HumanFallbackManager(Node):
    def __init__(self):
        super().__init__('human_fallback_manager')
        self.confidence = 1.0
        self.ttc = float('inf')
        self.ack_event = threading.Event()
        self.create_subscription(Float32, '/perception/confidence', self.conf_cb, 10)
        self.create_subscription(Float32, '/perception/ttc', self.ttc_cb, 10)
        self.cmd_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.safe_stop_pub = self.create_publisher(Bool, '/safe_stop', 10)
        self.get_logger().info("HumanFallbackManager initialized")

    def conf_cb(self, msg):
        self.confidence = float(msg.data)
        self.evaluate()

    def ttc_cb(self, msg):
        self.ttc = float(msg.data)
        self.evaluate()

    def evaluate(self):
        # If perception confidence low and imminent collision, request operator
        if self.confidence < CONFIDENCE_THRESHOLD and self.ttc < TTC_THRESHOLD:
            if not self.ack_event.is_set():
                self.get_logger().warn("Escalating to human operator")
                self.prompt_operator()
                # start timer thread to await ack
                timer = threading.Timer(OPERATOR_TIMEOUT, self._operator_timeout)
                timer.start()

    def prompt_operator(self):
        payload = {
            "vehicle_id": "robot_42",
            "timestamp": time.time(),
            "confidence": self.confidence,
            "ttc": self.ttc,
            # include compressed sensor context pointer or small image hash
        }
        # synchronous post; in deployment replace with async client and retries
        try:
            resp = requests.post(OPERATOR_ENDPOINT, json=payload, timeout=1.0)
            if resp.status_code == 200:
                self.get_logger().info("Operator prompt delivered")
            else:
                self.get_logger().error(f"Operator prompt failed {resp.status_code}")
        except requests.RequestException as e:
            self.get_logger().error(f"Signaling error: {e}")

    def operator_ack(self):
        # Called by external callback when operator accepts control
        self.ack_event.set()
        self.get_logger().info("Operator acknowledged control")

    def _operator_timeout(self):
        if not self.ack_event.is_set():
            self.get_logger().error("Operator did not respond in time; executing safe stop")
            self.execute_safe_stop()

    def execute_safe_stop(self):
        # Publish to low-level controller that executes immediate brake command
        self.safe_stop_pub.publish(Bool(data=True))
        stop = Twist()
        stop.linear.x = 0.0
        stop.angular.z = 0.0
        self.cmd_pub.publish(stop)

def main(args=None):
    rclpy.init(args=args)
    node = HumanFallbackManager()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()