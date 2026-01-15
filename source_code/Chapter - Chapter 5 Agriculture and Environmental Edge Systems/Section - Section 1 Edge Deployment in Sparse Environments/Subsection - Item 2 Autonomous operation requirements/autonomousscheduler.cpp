#include "Power.h"          // platform-specific power API
#include "Network.h"        // network stack: LoRaWAN/NB-IoT/Iridium
#include "TinyML.h"         // TFLite Micro wrapper
#include "Storage.h"        // circular buffer and wear-leveling

constexpr float E_MIN = 0.5f;   // Wh, reserve for safety actions
constexpr int SYNC_MAX_RETRIES = 5;
constexpr unsigned SYNC_BACKOFF_MS = 1000;

void run_inference() {
  // load windowed sensor data into model input
  if (!TinyML::Invoke()) { /* record failure and degrade model */ }
  auto decision = TinyML::GetDecision();
  if (decision.actuate) { Actuator::Trigger(decision.params); }
  Storage::AppendSummary(decision.summary); // compressed
}

void try_sync() {
  if (!Network::Available()) return;
  int retries = 0;
  while (retries < SYNC_MAX_RETRIES && Power::ReadWh() > E_MIN) {
    auto batch = Storage::PrepareBatch();
    if (Network::Transmit(batch)) { Storage::MarkUploaded(batch); return; }
    retries++;
    Power::SleepMs(SYNC_BACKOFF_MS << retries); // exponential backoff
  }
}

int main() {
  Power::Init(); Network::Init(); Storage::Init(); TinyML::Init();
  while (true) {
    float e = Power::ReadWh();
    if (e <= E_MIN) {
      // conserve: sample slower, avoid heavy compute/transmit
      Sensor::SleepMs(600000); continue;
    }
    Sensor::Sample();            // capture sensors at configured rate
    if (Sensor::WindowReady()) run_inference(); // local decision
    if (Network::WindowOpen()) try_sync();      // opportunistic upload
    Power::EnterLowPower();      // platform low-power idle (PM API)
  }
}