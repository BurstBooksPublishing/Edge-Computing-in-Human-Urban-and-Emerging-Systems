#include "FreeRTOS.h"
#include "task.h"
#include "timers.h"
#include "sensor.h"      // platform sensor API
#include "transport.h"   // LoRa/NB-IoT wrapper
#include "energy.h"      // simple energy model

#define NOMINAL_INTERVAL_MS 21600000UL  // 6 hours
#define HIGH_FREQ_MS        900000UL    // 15 minutes
#define ANOMALY_THRESH      0.05f       // domain-specific

static uint32_t interval_ms = NOMINAL_INTERVAL_MS;

void sampling_task(void *arg) {
    sensor_t s;
    energy_state_t e = energy_read();
    for (;;) {
        sensor_read(&s);                         // blocking or polled read
        float value = sensor_extract_value(&s); // e.g., soil moisture
        energy_consume(PER_SAMPLE_MJ);          // accounting

        // lightweight anomaly detector (replace with TinyML model)
        if (fabsf(value - sensor_running_mean()) > ANOMALY_THRESH) {
            // increase sampling fidelity
            interval_ms = HIGH_FREQ_MS;
            // try to transmit a concise event immediately
            if (energy_available() > PER_TX_MJ) {
                uint8_t payload[32];
                size_t len = pack_event(payload, value);
                transport_send(payload, len);    // platform-specific API
                energy_consume(PER_TX_MJ);
            }
        } else {
            // slowly decay to nominal interval
            interval_ms = NOMINAL_INTERVAL_MS;
        }

        energy_update_harvest();                 // read harvester state
        vTaskDelay(pdMS_TO_TICKS(interval_ms));
    }
}

// Create task in main()
/* xTaskCreate(sampling_task, "sampler", 1024, NULL, 2, NULL); */