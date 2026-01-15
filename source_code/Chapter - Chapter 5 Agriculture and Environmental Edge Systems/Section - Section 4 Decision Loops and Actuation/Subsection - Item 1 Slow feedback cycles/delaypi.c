/* Minimal delay-compensated PI for STM32L4, FreeRTOS.
   - adc_read_moisture(): platform ADC read (returns 0..1)
   - valve_set_pwm(duty): hardware PWM (0..1)
   - send_telemetry(): non-blocking uplink
   - CONFIG_DELAY_SLOTS: estimated delay in slots (hours/slot)
*/
#include "FreeRTOS.h"
#include "task.h"
#include 
#include 

#define CONFIG_DELAY_SLOTS 8
#define BUFFER_SIZE (CONFIG_DELAY_SLOTS+4)
static float cmd_buffer[BUFFER_SIZE];     // past u_{t}
static uint16_t buf_idx = 0;

static float Kp = 0.6f, Ki = 0.02f;       // tuned conservatively
static float integrator = 0.0f;
static const TickType_t slot_ms = 3600000 / portTICK_PERIOD_MS; // 1 hour slot

static float adc_read_moisture(void);     // provided by board code
static void valve_set_pwm(float duty);    // provided by board code
static void send_telemetry(void);         // provided by board code

/* Simple predictor: first-order model y_{t+1} = a*y_t + b*u_{t-d} */
static float model_a = 0.98f, model_b = 0.05f;

static void control_task(void *arg) {
    float setpoint = 0.35f; // target soil moisture
    float y = adc_read_moisture();
    /* initialize buffer to zeros */
    memset(cmd_buffer, 0, sizeof(cmd_buffer));
    for (;;) {
        vTaskDelay(slot_ms);               // wake once per slot
        y = adc_read_moisture();           // current measurement
        /* Predict future measurement assuming pending commands in buffer */
        float y_pred = y;
        for (uint16_t i=0;i 10.0f) integrator = 10.0f;
        if (integrator < -10.0f) integrator = -10.0f;
        float u = Kp * err + Ki * integrator;
        if (u < 0.0f) u = 0.0f;
        if (u > 1.0f) u = 1.0f;
        /* store command into buffer at current write position */
        cmd_buffer[buf_idx] = u;
        buf_idx = (buf_idx + 1) % BUFFER_SIZE;
        /* actuate only when command reaches actuator slot (delay consumed) */
        /* actuator_slot = (buf_idx + BUFFER_SIZE - CONFIG_DELAY_SLOTS) % BUFFER_SIZE */
        uint16_t actuator_slot = (buf_idx + BUFFER_SIZE - CONFIG_DELAY_SLOTS) % BUFFER_SIZE;
        valve_set_pwm(cmd_buffer[actuator_slot]);  // hardware PWM
        send_telemetry();                           // non-blocking uplink
    }
}

void start_control(void) {
    xTaskCreate(control_task,"ctrl",1024,NULL,3,NULL);
}