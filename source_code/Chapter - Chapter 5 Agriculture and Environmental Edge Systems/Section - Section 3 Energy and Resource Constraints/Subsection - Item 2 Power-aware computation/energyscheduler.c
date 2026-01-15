#include "FreeRTOS.h"
#include "task.h"
#include "adc.h"        // platform ADC API
#include "power.h"      // battery and solar read helpers
#include "tflm_infer.h" // tensorflite micro wrapper
#include "radio.h"      // LoRa/NB-IoT transmit API

#define V_BATT_HIGH 3.9f
#define V_BATT_LOW  3.4f
#define SAMPLE_HIGH_MS 1000U
#define SAMPLE_LOW_MS  15000U

static void energy_task(void *pv) {
    uint32_t sample_interval = SAMPLE_HIGH_MS;
    for (;;) {
        float vbatt = read_battery_voltage();          // ADC read
        float p_h   = estimate_harvest_power();       // solar estimator
        // simple hysteretic policy
        if (vbatt > V_BATT_HIGH && p_h > 15.0f) {
            sample_interval = SAMPLE_HIGH_MS;         // frequent sampling
            tflm_select_model(MODEL_FULL);            // higher-accuracy model
        } else if (vbatt < V_BATT_LOW || p_h < 2.0f) {
            sample_interval = SAMPLE_LOW_MS;          // conserve energy
            tflm_select_model(MODEL_TINY);            // compressed model
        }
        // perform sampling and inference
        sensor_sample_t s = sensor_read();            // ADC, IMU, camera collector
        inference_result_t r = tflm_infer(&s);        // local inference call
        if (r.confidence > 0.8f && vbatt > V_BATT_LOW) {
            radio_send_compact(&r);                    // transmit only high-value events
        } else {
            // accumulate local logs for bulk upload when energy permits
            store_local(&r);
        }
        // adapt duty via vTaskDelay; use low-power tickless idle on Zephyr/FreeRTOS PM
        vTaskDelay(pdMS_TO_TICKS(sample_interval));
    }
}

int main(void) {
    platform_init();                                 // clocks, ADC, radio, TFLM init
    xTaskCreate(energy_task, "energy", 4096, NULL, 2, NULL);
    vTaskStartScheduler();
    for (;;) {}
}