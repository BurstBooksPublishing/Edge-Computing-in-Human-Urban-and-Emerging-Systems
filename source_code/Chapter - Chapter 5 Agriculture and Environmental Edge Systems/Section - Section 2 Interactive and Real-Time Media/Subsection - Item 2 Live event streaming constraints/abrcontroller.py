#!/usr/bin/env python3
# Production-ready: uses exponential smoothing, safe bitrate bounds, and HTTP API to encoder.
import time, logging
import psutil, requests

ENCODER_API = "http://127.0.0.1:8080/api/encoder/bitrate"  # encoder management endpoint
IFACE = "eth0"                                        # monitored egress interface
SMOOTH_ALPHA = 0.3
MIN_BITRATE = 500_000    # 500 kbps
MAX_BITRATE = 8_000_000  # 8 Mbps
POLL_INTERVAL = 1.0      # seconds

logging.basicConfig(level=logging.INFO)
def get_iface_bytes(iface):
    counters = psutil.net_io_counters(pernic=True)
    return counters[iface].bytes_sent + counters[iface].bytes_recv

def set_encoder_bitrate(bps):
    # Send a request to encoder control API (assumes JSON interface and auth handled externally)
    payload = {"target_bitrate": int(bps)}
    r = requests.post(ENCODER_API, json=payload, timeout=1.0)
    r.raise_for_status()

def main():
    last_bytes = get_iface_bytes(IFACE)
    smoothed_bw = None
    current_target = MAX_BITRATE
    set_encoder_bitrate(current_target)
    logging.info("Initial bitrate set: %d", current_target)
    while True:
        time.sleep(POLL_INTERVAL)
        now_bytes = get_iface_bytes(IFACE)
        bandwidth_bps = ((now_bytes - last_bytes) * 8) / POLL_INTERVAL
        last_bytes = now_bytes
        smoothed_bw = bandwidth_bps if smoothed_bw is None else (SMOOTH_ALPHA*bandwidth_bps + (1-SMOOTH_ALPHA)*smoothed_bw)
        # conservative margin for overhead and retransmit
        margin = 0.8
        allowed = smoothed_bw * margin
        target = max(MIN_BITRATE, min(MAX_BITRATE, allowed))
        # Hysteresis to avoid flapping
        if abs(target - current_target) / current_target > 0.10:
            try:
                set_encoder_bitrate(target)
                current_target = target
                logging.info("Updated encoder bitrate to %d (measured bw %.0f)", current_target, smoothed_bw)
            except Exception as e:
                logging.error("Failed to set bitrate: %s", e)

if __name__ == "__main__":
    main()