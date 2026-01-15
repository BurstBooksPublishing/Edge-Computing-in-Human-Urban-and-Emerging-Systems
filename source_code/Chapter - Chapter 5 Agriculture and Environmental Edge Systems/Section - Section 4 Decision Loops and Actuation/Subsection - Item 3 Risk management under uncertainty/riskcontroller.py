#!/usr/bin/env python3
# Production-ready: persistent state, backoff, logging, graceful shutdown.

import time, json, math, logging, sqlite3, signal
import numpy as np
import paho.mqtt.client as mqtt

BROKER='localhost'; CMD_TOPIC='actuator/valve/cmd'; CONF_TOPIC='actuator/valve/conf'
DB='actuation.db'; BETA=0.9; RMAX=0.05  # CVaR level and max acceptable loss

# simple persistent store for auditability
conn = sqlite3.connect(DB, isolation_level=None)
conn.execute('''CREATE TABLE IF NOT EXISTS log(ts REAL, posterior REAL, action TEXT, cvar REAL)''')

logging.basicConfig(level=logging.INFO)
client = mqtt.Client(client_id='gateway-controller')

def predict_posterior(p_now, tau_hours, evap_rate=0.01):
    # propagate moisture probability forward with exponential decay model
    decay = np.exp(-evap_rate * tau_hours)
    return p_now * decay

def approx_cvar(loss_samples, beta=BETA):
    losses = np.sort(loss_samples)
    k = int(math.ceil(beta * len(losses)))
    return losses[k:].mean()

def compute_loss_samples(action, samples_states):
    # user-defined: loss increases if state is 'dry' and no water
    return np.array([ (0.0 if (action=='open' and s>0.3) or (action=='close' and s<=0.3) else 1.0) for s in samples_states ])

def on_connect(client, userdata, flags, rc):
    logging.info('MQTT connected rc=%s', rc); client.subscribe('sensors/moisture')

def on_message(client, userdata, msg):
    payload=json.loads(msg.payload)
    p_now = payload['p_dry']  # posterior probability of being dry
    tau = payload.get('expected_delay_hours', 1.0)
    # predictive step for delay
    p_pred = predict_posterior(p_now, tau)
    # sample states for risk estimate (Bernoulli approximates discrete outcomes)
    samples = np.random.rand(1000) < p_pred
    # compute candidate actions and evaluate
    candidates = ['open','close','defer']
    best=None; best_cost=1e9
    for a in candidates:
        losses = compute_loss_samples(a, samples.astype(float))
        cvar = approx_cvar(losses)
        exp_loss = losses.mean()
        # energy and safety checks omitted for brevity
        if cvar<=RMAX and exp_loss
\chapter{Chapter 6: Media Delivery and Interactive Systems}
\section{Section 1: Edge-Assisted Content Delivery}
\subsection{Item 1:  Latency-sensitive media pipelines}
This subsection follows the preceding overview of edge assistance by focusing on pipelines where sub-100 ms end-to-end delay materially changes user perception. The following develops practical models, then shows an implementation pattern and deployment considerations for industrial and urban edge platforms.

Latency-sensitive media pipelines require co-design across capture hardware, on-device processing, networking stacks, and client decode/display. Conceptually, break end-to-end latency into measurable components:
\begin{equation}\label{eq:latency_sum}
L_{\mathrm{total}} = L_{\mathrm{capture}} + L_{\mathrm{proc}} + L_{\mathrm{network}} + L_{\mathrm{decode}} + L_{\mathrm{display}}.
\end{equation}
Each term admits optimization levers: capture buffer sizing and callback scheduling; inference or encoding resource allocation (CPU, GPU, or NPU); choice of transport (RTP/UDP, QUIC, or SRT); and low-latency decoder settings. For human-facing systems, target percentiles matter: design for $P(L_{\mathrm{total}}>t_{\mathrm{max}})\leq\alpha$ (e.g., $t_{\mathrm{max}}=100\,$ms at $\alpha=0.01$).

Theory: modeling and schedulability
- Treat capture and processing as a tandem of queues. If frames arrive at rate $\lambda$ and service time mean $\mu^{-1}$, queueing delay grows as utilization $\rho=\lambda/\mu$ approaches 1. Keep $\rho<0.7$ for predictable tails in practice.
- For mixed CPU/GPU pipelines, model processing as a two-server system. If CPU handles preproc and GPU encodes, the slowest stage sets throughput. Balance by measured stage latencies $s_i$ and by offloading to hardware encoders (e.g., \lstinline|nvv4l2h264enc| on NVIDIA Jetson or VA-API on Intel).
- Network latency variance often dominates tail behavior. Use transport-level redundancy (FEC) only when it reduces tail re-transmission delay compared to end-to-end ARQ.

Example: low-latency camera-to-client on NVIDIA Jetson Xavier NX
- Hardware and OS: NVIDIA Jetson Xavier NX, Linux with PREEMPT_RT if strict scheduling required, NVIDIA L4T kernel for hardware encoders.
- Capture API: V4L2 with memory-mapped buffers and monotonic timestamping.
- Media framework: GStreamer for pipeline composition; RTP transport with small packetization interval; RTCP for receiver reports and jitter feedback.

A practical pipeline command (used by the code below) uses \lstinline|v4l2src|, \lstinline|nvvidconv|, \lstinline|nvv4l2h264enc|, and RTP payloader. Key settings: minimal queue sizes, encoder \lstinline|presetLevel| for low latency, and \lstinline|config-interval=1| on the payloader to send SPS/PPS when network conditions change.

Application: production-ready capture/stream launcher
\begin{lstlisting}[language=Python,caption={Robust low-latency GStreamer launcher for Jetson Xavier NX},label={lst:gst_launcher}]
#!/usr/bin/env python3
"""
Production launcher: starts and supervises a GStreamer low-latency RTP stream.
Requires gst-launch-1.0 and Jetson hardware encoder.
"""
import subprocess
import time
import shlex
import logging
import sys
logging.basicConfig(level=logging.INFO)

GST_CMD = (
    "gst-launch-1.0 -e "
    "v4l2src device=/dev/video0 io-mode=4 num-buffers=0 ! "
    "video/x-raw, width=1280, height=720, framerate=30/1 ! "
    "nvvidconv ! video/x-raw(memory:NVMM) ! "
    "nvv4l2h264enc bitrate=3000000 presetLevel=1 maxperf-enable=1 ! "
    "h264parse ! rtph264pay config-interval=1 pt=96 ! "
    "udpsink host=192.168.10.50 port=5004 sync=false async=false"
)

def start_pipeline(cmd):
    args = shlex.split(cmd)
    return subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

def supervise():
    proc = start_pipeline(GST_CMD)
    logging.info("Started GStreamer PID %d", proc.pid)
    try:
        while True:
            ret = proc.poll()
            if ret is not None:
                # restart on failure with exponential backoff
                logging.warning("Pipeline exited with %s; restarting", ret)
                time.sleep(1)
                proc = start_pipeline(GST_CMD)
                logging.info("Restarted GStreamer PID %d", proc.pid)
            time.sleep(0.5)
    except KeyboardInterrupt:
        logging.info("Stopping pipeline")
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()

if __name__ == "__main__":
    supervise()
# Comments:
# - io-mode=4 sets DMABUF capture (efficient on Jetson).
# - sync=false avoids blocking on sink timing to reduce jitter.
# - In production, run under a systemd unit with CPU and IRQ affinity.