#include 
#include 
#include 

// OffloadDecider: keeps rolling estimates and checks offload inequality.
// Integrate with network telemetry (RTT in ms) and edge-reported render_time (ms).
class OffloadDecider {
public:
    OffloadDecider(double safety_margin_ms = 5.0);

    // Update measured components (call from IO / render threads)
    void update_local_render_time(double ms);     // measured on-device full-frame render
    void update_network_rtt(double ms);           // measured RTT to chosen edge node
    void update_remote_render_time(double ms);    // edge reports expected render time
    void update_decode_time(double ms);           // measured decode + composite time

    // Should the client offload the next frame?
    bool should_offload() const;

private:
    mutable std::mutex mtx_;
    double local_render_ms_;
    double network_rtt_ms_;
    double remote_render_ms_;
    double decode_ms_;
    double safety_margin_ms_;
};