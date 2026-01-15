#include 
#include 
#include 
#include 
#include 

// Simple production-ready estimator and scheduler.
// - update() is called with (remote_event_time_ns, local_receive_time_ns).
// - schedulePresentation() returns a steady_clock time_point to present at.
class ClockSync {
public:
    ClockSync(double alpha = 0.02) : alpha_(alpha), initialized_(false), offset_ns_(0.0) {}

    // Remote timestamp and local monotonic receive time (both in ns).
    void update(int64_t remote_ts_ns, int64_t local_recv_ns) {
        std::lock_guard lk(mutex_);
        double sample_offset = static_cast(remote_ts_ns) - static_cast(local_recv_ns);
        if (!initialized_) {
            offset_ns_ = sample_offset;
            initialized_ = true;
        } else {
            offset_ns_ = alpha_ * sample_offset + (1.0 - alpha_) * offset_ns_;
        }
    }

    // Compute local steady_clock presentation target for a desired remote time.
    std::chrono::steady_clock::time_point schedulePresentation(int64_t desired_remote_ts_ns,
                                                               int64_t render_latency_ns = 0) {
        std::lock_guard lk(mutex_);
        // Convert remote time to local monotonic by subtracting offset and accounting render latency.
        double local_target_ns = static_cast(desired_remote_ts_ns) - offset_ns_ - static_cast(render_latency_ns);
        auto now = std::chrono::steady_clock::now();
        int64_t now_ns = std::chrono::duration_cast(now.time_since_epoch()).count();
        int64_t wait_ns = static_cast(std::round(local_target_ns)) - now_ns;
        if (wait_ns < 0) wait_ns = 0; // Present immediately if late.
        return now + std::chrono::nanoseconds(wait_ns);
    }

private:
    double alpha_;
    bool initialized_;
    double offset_ns_;
    std::mutex mutex_;
};