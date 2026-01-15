#include 
#include 
#include 
#include 
#include 
#include 
#include 

#define GPIO_CHIP "/dev/gpiochip0"
#define OVERRIDE_LINE 17           // adjust per hardware
#define LOGFILE "/var/log/override_audit.log"
#define MQTT_BROKER "mqtt.example.local"
#define MQTT_PORT 8883
#define MQTT_TOPIC "fleet/override"

// atomic append with fsync; returns 0 on success
static int audit_log(const char *msg) {
    FILE *f = fopen(LOGFILE, "a");
    if (!f) return -1;
    fprintf(f, "%s\n", msg);
    fflush(f);
    fsync(fileno(f));
    fclose(f);
    return 0;
}

// publish a message over TLS-secured MQTT (synchronous for simplicity)
static int publish_mqtt(const char *payload) {
    struct mosquitto *mosq = mosquitto_new(NULL, true, NULL);
    if (!mosq) return -1;
    // set TLS - production: set proper CA/cert/key and verify options
    mosquitto_tls_set(mosq, "/etc/ssl/ca.pem", NULL, "/etc/ssl/client.crt", "/etc/ssl/client.key", NULL);
    mosquitto_tls_insecure_set(mosq, false);
    if (mosquitto_connect(mosq, MQTT_BROKER, MQTT_PORT, 60)) {
        mosquitto_destroy(mosq); return -1;
    }
    mosquitto_publish(mosq, NULL, MQTT_TOPIC, strlen(payload), payload, 1, true);
    mosquitto_disconnect(mosq); mosquitto_destroy(mosq);
    return 0;
}

int main(void) {
    struct gpiod_chip *chip = gpiod_chip_open(GPIO_CHIP);
    struct gpiod_line *line;
    struct timespec ts;
    char msg[256];

    if (!chip) return 1;
    line = gpiod_chip_get_line(chip, OVERRIDE_LINE);
    gpiod_line_request_input(line, "override_handler");

    while (1) {
        int val = gpiod_line_get_value(line);
        if (val == 1) { // button asserted
            // simple debounce
            usleep(20000);
            if (gpiod_line_get_value(line) == 1) {
                clock_gettime(CLOCK_REALTIME, &ts);
                snprintf(msg, sizeof(msg), "{\"ts\":%ld,\"event\":\"override\",\"source\":\"local\"}", ts.tv_sec);
                // immediate hardware inhibit should be asserted here via dedicated safe path
                audit_log(msg);          // durable audit trail
                publish_mqtt(msg);       // notify fleet management
                // block until button released to avoid repeated triggers
                while (gpiod_line_get_value(line) == 1) usleep(100000);
            }
        }
        usleep(10000);
    }
    gpiod_chip_close(chip);
    return 0;
}