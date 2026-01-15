#include 
#include 
#include 
#include "tensorrt_infer.hpp" // production TensorRT wrapper (thread-safe)
#include "can_actuator.hpp"   // SocketCAN wrapper (non-blocking, realtime-safe)

using namespace std::chrono_literals;

class PercepActNode : public rclcpp::Node {
public:
  PercepActNode()
  : Node("percep_act"), infer_(/*engine path*/"/opt/models/net.trt"),
    can_("/dev/can0")
  {
    // Real-time callback group for deterministic scheduling.
    rclcpp::CallbackGroupOptions opts;
    cbg_ = this->create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive, opts);
    auto qos = rclcpp::QoS(1).reliable().keep_last(1);
    img_sub_ = this->create_subscription(
      "camera/image_raw", qos,
      std::bind(&PercepActNode::image_cb, this, std::placeholders::_1),
      cbg_);
    deadline_ms_ = this->declare_parameter("loop_deadline_ms", 50);
  }

private:
  void image_cb(const sensor_msgs::msg::Image::SharedPtr msg) {
    auto t0 = this->now();
    // Minimal preprocessing on pinned memory; avoid copies.
    InferenceInput in = preprocessImageRT(msg);
    auto result = infer_.run(in); // optimized TensorRT synchronous call
    // Compute actuation command deterministically.
    ActCmd cmd = control_from_percept(result);
    // Deadline check: drop or degrade if exceeded.
    auto elapsed = (this->now() - t0).nanoseconds() / 1e6; // ms
    if (elapsed > deadline_ms_) {
      RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 1000,
                          "Missed deadline: %.2f ms", elapsed);
      // degrade: switch to conservative safe-stop or lower-speed command
      cmd = safe_degrade(cmd);
    }
    can_.send_nonblocking(cmd); // non-blocking, real-time safe transmit
  }

  rclcpp::Subscription::SharedPtr img_sub_;
  rclcpp::CallbackGroup::SharedPtr cbg_;
  TensorRTWrapper infer_;
  CanActuator can_;
  int deadline_ms_;
};

int main(int argc, char** argv) {
  rclcpp::init(argc, argv);
  // Configure realtime scheduling externally (systemd slice or chrt).
  rclcpp::spin(std::make_shared());
  rclcpp::shutdown();
  return 0;
}