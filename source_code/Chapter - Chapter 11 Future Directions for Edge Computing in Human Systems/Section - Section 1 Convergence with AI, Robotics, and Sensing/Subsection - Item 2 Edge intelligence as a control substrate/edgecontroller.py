#!/usr/bin/env python3
import time, asyncio, socket
import numpy as np
import rclpy
from rclpy.node import Node
import onnxruntime as ort
from std_msgs.msg import Float32MultiArray

# ROS 2 node that subscribes to sensor summaries, runs model, and sends actuators.
class EdgeController(Node):
    def __init__(self):
        super().__init__('edge_controller')
        self.sub = self.create_subscription(
            Float32MultiArray, 'sensor_summary', self.cb_sensor, 10)
        self.model = ort.InferenceSession('/opt/models/controller.onnx',
                                          providers=['TensorrtExecutionProvider','CPUExecutionProvider'])
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.actuator_addr = ('192.168.1.50', 9000)
        self.latency_ema = 0.05  # exponential moving average of round-trip latency
        self.alpha = 0.1
        self.seq = 0
        self.watchdog_timeout = 1.0  # safety timeout seconds

    def cb_sensor(self, msg):
        t0 = time.monotonic()
        inp = np.array(msg.data, dtype=np.float32).reshape(1, -1)
        out = self.model.run(None, {'input': inp})[0]  # on-device inference
        cmd = self._format_actuator(out)
        # embed timestamp and sequence number for actuator-side RTT check
        payload = cmd.tobytes()
        header = f'{self.seq},{t0}'.encode()
        self.udp.sendto(header + b'|' + payload, self.actuator_addr)
        self.seq += 1
        # estimate one-way latency by heuristic (actuator echoes header periodically)
        # (assume actuator echoes header; production systems use ACKs with timestamps)
        rtt = self._probe_rtt()
        self.latency_ema = self.alpha * rtt + (1-self.alpha)*self.latency_ema
        self._safety_check()

    def _format_actuator(self, out):
        # map model output to actuator command vector (implementation-specific)
        return np.clip(out.astype(np.float32), -1.0, 1.0)

    def _probe_rtt(self):
        # non-blocking RTT probe; lightweight implementation
        try:
            self.udp.settimeout(0.01)
            probe = b'ping'
            t0 = time.monotonic()
            self.udp.sendto(b'probe|' + probe, self.actuator_addr)
            _data, _ = self.udp.recvfrom(256)
            return time.monotonic() - t0
        except socket.timeout:
            return 1.0  # conservative large RTT
        finally:
            self.udp.settimeout(None)

    def _safety_check(self):
        # degrade control if latency grows beyond bound from (1)
        T_sample = 0.1  # example sampling period
        f_c = 1.0       # targeted bandwidth
        if f_c * (T_sample + self.latency_ema) > 0.45:
            self.get_logger().warn('High latency: switching to safe fallback')
            # send safe plan or increase local autonomy here

def main(args=None):
    rclpy.init(args=args)
    node = EdgeController()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()