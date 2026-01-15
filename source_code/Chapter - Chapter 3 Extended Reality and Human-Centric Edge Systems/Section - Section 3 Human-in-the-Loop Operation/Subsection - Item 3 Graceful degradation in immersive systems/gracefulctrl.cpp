#include 
#include 
#include "RenderManager.h" // platform-specific: OpenXR binding wrapper
#include "NetMonitor.h"    // reports bandwidth, jitter
#include "SysMonitor.h"    // CPU/GPU usage
#include 

using json = nlohmann::json;
using namespace std::chrono_literals;

int main() {
    RenderManager renderer; // provides setResolution(), setFoveation(), setFrameRate()
    NetMonitor net;         // provides bandwidth_kbps(), rtt_ms()
    SysMonitor sys;         // provides cpu_pct(), gpu_pct()
    json cfg = json::parse(R"({
        "latency_threshold_ms":20, "min_frame_rate":30, "max_frame_rate":90,
        "safe_cpu_margin":0.8, "low_bandwidth_kbps":500
    })");

    while (true) {
        auto bw = net.bandwidth_kbps();
        auto rtt = net.rtt_ms();
        auto cpu = sys.cpu_pct();
        auto gpu = sys.gpu_pct();

        // Safety check: if RTT or CPU exceed safety, enter safe freeze mode
        if (rtt > 150 || cpu > cfg["safe_cpu_margin"].get()*100) {
            renderer.setFrameRate(cfg["min_frame_rate"]);
            renderer.setFoveation(0.9f); // aggressive foveation
            renderer.disableShadows();   // reduce GPU load
            renderer.setTransportPolicy(RenderManager::Transport::KeyframeOnly);
            std::this_thread::sleep_for(100ms);
            continue;
        }

        // Bandwidth-based graceful steps
        if (bw < cfg["low_bandwidth_kbps"]) {
            renderer.setResolution(720, 720);
            renderer.setFrameRate(30);
            renderer.enableHEVC(true); // compress keyframes
            renderer.setFoveation(0.7f);
        } else if (gpu > 85) {
            renderer.setResolution(1080, 1080);
            renderer.setFrameRate(45);
            renderer.setFoveation(0.5f);
        } else {
            renderer.setResolution(1440, 1600);
            renderer.setFrameRate(72);
            renderer.setFoveation(0.2f);
            renderer.enableHEVC(false);
        }

        // Small control period
        std::this_thread::sleep_for(50ms);
    }
    return 0;
}