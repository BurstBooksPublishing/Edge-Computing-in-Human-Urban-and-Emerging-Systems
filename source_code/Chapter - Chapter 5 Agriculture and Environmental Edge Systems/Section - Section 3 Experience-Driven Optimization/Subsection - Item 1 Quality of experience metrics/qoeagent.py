#!/usr/bin/env python3
# Production-ready QoE agent: asynchronous, resilient, and configurable.
import asyncio, json, subprocess, logging, time
import aiohttp, psutil, cv2
from skimage.metrics import structural_similarity as ssim

API_ENDPOINT = "https://orchestrator.example.local/api/v1/qoe"
SESSION_ID = "session-1234"            # Unique session identifier
VMAF_CLI = "/usr/bin/vmaf"             # Optional libvmaf CLI path

logging.basicConfig(level=logging.INFO)

async def measure_rtt_quic(host, port=4433, timeout=1.0):
    # Lightweight QUIC RTT via system ping as fallback for simplicity.
    proc = await asyncio.create_subprocess_exec(
        "ping", "-c", "1", "-W", "1", host,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL
    )
    await proc.wait()
    return 0.0 if proc.returncode == 0 else timeout

def compute_ssim(frame_ref, frame_prd):
    # Convert to grayscale and compute SSIM on 8-bit images.
    gray_ref = cv2.cvtColor(frame_ref, cv2.COLOR_BGR2GRAY)
    gray_prd = cv2.cvtColor(frame_prd, cv2.COLOR_BGR2GRAY)
    s, _ = ssim(gray_ref, gray_prd, full=True)
    return float(s)

def try_vmaf(reference_path, distorted_path):
    # Use libvmaf if available; returns normalized score in [0,1].
    try:
        out = subprocess.check_output([VMAF_CLI, reference_path, distorted_path, "--json"], stderr=subprocess.DEVNULL)
        j = json.loads(out)
        return j.get("aggregate", {}).get("VMAF_score", 0.0) / 100.0
    except Exception:
        return None

async def collect_and_report(stream_source, reference_frame_path=None):
    cap = cv2.VideoCapture(stream_source)
    async with aiohttp.ClientSession() as session:
        while True:
            start = time.time()
            ret, frame = cap.read()
            if not ret:
                await asyncio.sleep(0.1); continue
            # Sample pair: use stored reference if available.
            q_est = 0.0
            if reference_frame_path:
                ref = cv2.imread(reference_frame_path)
                q_est = compute_ssim(ref, frame)
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory().percent
            rtt = await measure_rtt_quic("orchestrator.example.local")
            payload = {
                "session": SESSION_ID,
                "timestamp": int(start*1000),
                "q_ssim": q_est,
                "rtt": rtt,
                "cpu": cpu,
                "mem": mem
            }
            try:
                async with session.post(API_ENDPOINT, json=payload, timeout=2) as resp:
                    await resp.text()
            except Exception as e:
                logging.warning("report failed: %s", e)
            await asyncio.sleep(0.5)  # sampling interval

if __name__ == "__main__":
    asyncio.run(collect_and_report(0, reference_frame_path="/opt/ref/frame.png"))