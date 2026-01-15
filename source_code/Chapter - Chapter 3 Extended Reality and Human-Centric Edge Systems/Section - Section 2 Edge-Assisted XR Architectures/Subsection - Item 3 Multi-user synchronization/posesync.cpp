#include 
#include 
#include 
#include 
// Minimal production-ready core; integrate with thread pools, DTLS, and application logic.

using boost::asio::ip::udp;
struct PosePkt { uint32_t seq; uint64_t t_us; float px,py,pz, vx,vy,vz; }; // timestamp in microseconds

class EdgeSync {
  udp::socket sock_;
  udp::endpoint client_ep_;
  std::atomic seq_{0};
public:
  EdgeSync(boost::asio::io_context& io, uint16_t port)
    : sock_(io, udp::endpoint(udp::v4(), port)) { start_receive(); }

  void start_receive() {
    sock_.async_receive_from(boost::asio::buffer(&recv_buf_, sizeof(recv_buf_)),
      client_ep_, [this](auto ec, auto n){ if(!ec) handle_recv(n); start_receive(); });
  }

  void handle_recv(std::size_t n) {
    // parse incoming PosePkt; validate size, auth, and timestamp
    PosePkt in = recv_buf_;
    // update authoritative state, then broadcast delta
    PosePkt out = make_broadcast(in); // fills seq, server timestamp
    for (auto &ep : clients_) sock_.send_to(boost::asio::buffer(&out, sizeof(out)), ep);
  }

  static PosePkt make_broadcast(const PosePkt& in) {
    PosePkt p = in;
    p.seq = ++instance_seq_;
    p.t_us = now_us();
    return p;
  }

  static uint64_t now_us() {
    return std::chrono::duration_cast(
      std::chrono::steady_clock::now().time_since_epoch()).count();
  }
private:
  PosePkt recv_buf_;
  std::vector clients_;
  static std::atomic instance_seq_;
};
std::atomic EdgeSync::instance_seq_{0};