#!/usr/bin/env python3
import subprocess, time, psutil, math, signal, sys
# Configurable renditions: (bitrate_kbps, width, height)
RENDITIONS = [(2000,1280,720),(1200,854,480),(600,640,360),(300,426,240)]
SAFETY_FACTOR = 0.85          # leave headroom for bursts
EWMA_ALPHA = 0.2              # bandwidth estimator weight
GPU_LOAD_LIMIT = 0.80         # avoid >80% GPU load
FFMPEG_BIN = "/usr/bin/ffmpeg"
INPUT_SRC = "/dev/video0"
class ABRController:
    def __init__(self):
        self.ewma_bw = 5000.0   # initial kbps
        self.proc = None
    def measure_bandwidth(self):
        # lightweight active probe: send small HTTP range fetch to edge server
        start = time.time()
        p = subprocess.run(["/usr/bin/curl","-s","-o","/dev/null","-w","%{speed_download}","https://edge.example/warmup.bin"],
                           stdout=subprocess.PIPE, timeout=2)
        kbps = float(p.stdout.decode())*8/1000.0 if p.returncode==0 else self.ewma_bw
        self.ewma_bw = EWMA_ALPHA*kbps + (1-EWMA_ALPHA)*self.ewma_bw
        return self.ewma_bw
    def gpu_load(self):
        # parse tegrastats or nvidia-smi; here use NVML via psutil fallback (platform dependent)
        try:
            out = subprocess.check_output(["nvidia-smi","--query-gpu=utilization.gpu","--format=csv,noheader,nounits"])
            return float(out.decode().strip())/100.0
        except Exception:
            return 0.5
    def choose_rendition(self, bw_kbps, gpu_load):
        limit = bw_kbps*SAFETY_FACTOR
        for br,w,h in RENDITIONS:
            if br <= limit and (gpu_load + 0.05) < GPU_LOAD_LIMIT:  # small margin for encoder overhead
                return (br,w,h)
        return RENDITIONS[-1]
    def launch_ffmpeg(self, br,w,h):
        if self.proc:
            self.proc.send_signal(signal.SIGHUP)  # gentle reload for FFmpeg isn't standard; restart
            self.proc.kill()
            self.proc.wait()
        cmd = [
            FFMPEG_BIN, "-f","v4l2","-framerate","30","-video_size",f"{w}x{h}",
            "-i",INPUT_SRC,
            "-c:v","h264_nvenc","-b:v",f"{br}k","-maxrate",f"{br}k","-bufsize",f"{2*br}k",
            "-g","60","-f","flv","rtmp://edge.example/live/stream"
        ]
        self.proc = subprocess.Popen(cmd)  # production should add logging and health checks
    def run(self, interval=2.0):
        try:
            while True:
                bw = self.measure_bandwidth()
                gpu = self.gpu_load()
                br,w,h = self.choose_rendition(bw,gpu)
                self.launch_ffmpeg(br,w,h)
                time.sleep(interval)
        except KeyboardInterrupt:
            if self.proc: self.proc.kill()
if __name__=="__main__":
    ABRController().run()