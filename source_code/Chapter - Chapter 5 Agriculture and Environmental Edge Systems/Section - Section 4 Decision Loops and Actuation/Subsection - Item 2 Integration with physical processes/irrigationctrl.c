#include 
#include 
#include 
#include 
#include "kalman.h"     // compact Kalman filter implementation
#include "power.h"      // solar/battery management API

#define SENSE_PERIOD_MS  300000  // 5 minutes
#define VALVE_PIN        15
#define VALVE_DEV        "GPIO_0"

void control_task(void)
{
    const struct device *valve = device_get_binding(VALVE_DEV);
    const struct device *moist = device_get_binding("MOIST_SENSOR");
    struct kalman_state kf = kalman_init(1.0f, 0.1f); // Q,R tuned in lab
    gpio_pin_configure(valve, VALVE_PIN, GPIO_OUTPUT_INACTIVE);

    while (1) {
        sensor_sample_fetch(moist);                          // read sensor
        int16_t raw;
        sensor_channel_get(moist, SENSOR_CHAN_ALL, &raw);
        float meas = convert_raw_to_volumetric(raw);        // calibrated conversion
        float est = kalman_update(&kf, meas);               // one-step KF

        // simple constrained PI policy as fallback to MPC
        float error = est - target_moisture();
        float u = saturate(-Kp*error - Ki*kf.integral, 0.0f, 1.0f); // [0,1] valve fraction

        // enforce minimum on/off and safety interlocks
        if (!power_is_ok() || soil_temp_below_freeze()) u = 0.0f;
        apply_valve_fraction(valve, VALVE_PIN, u);          // PWM or duty control
        telemetry_publish("moisture", est);                 // send to gateway, buffered

        k_sleep(K_MSEC(SENSE_PERIOD_MS));
    }
}