#include "OffloadDecider.h"

OffloadDecider::OffloadDecider(double safety_margin_ms)
  : local_render_ms_(20.0),
    network_rtt_ms_(10.0),
    remote_render_ms_(12.0),
    decode_ms_(4.0),
    safety_margin_ms_(safety_margin_ms) {}

void OffloadDecider::update_local_render_time(double ms) {
    std::lock_guard g(mtx_);
    local_render_ms_ = 0.9 * local_render_ms_ + 0.1 * ms; // exponential smoothing
}
void OffloadDecider::update_network_rtt(double ms) {
    std::lock_guard g(mtx_);
    network_rtt_ms_ = 0.9 * network_rtt_ms_ + 0.1 * ms;
}
void OffloadDecider::update_remote_render_time(double ms) {
    std::lock_guard g(mtx_);
    remote_render_ms_ = 0.9 * remote_render_ms_ + 0.1 * ms;
}
void OffloadDecider::update_decode_time(double ms) {
    std::lock_guard g(mtx_);
    decode_ms_ = 0.9 * decode_ms_ + 0.1 * ms;
}

bool OffloadDecider::should_offload() const {
    std::lock_guard g(mtx_);
    double remote_path = network_rtt_ms_ + remote_render_ms_ + decode_ms_;
    return remote_path + safety_margin_ms_ < local_render_ms_;
}