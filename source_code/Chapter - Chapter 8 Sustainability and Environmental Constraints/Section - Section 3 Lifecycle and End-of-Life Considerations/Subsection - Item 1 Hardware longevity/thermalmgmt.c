/* Thermal-aware control loop: read CPU temp, reduce max_freq if needed,
   publish telemetry via MQTT. Build with: gcc thermal_mgmt.c -lmosquitto -o thermal_mgmt */
#include 
#include 
#include 
#include 
#include 
#define TEMP_PATH "/sys/class/thermal/thermal_zone0/temp"
#define SCALING_MAX_FREQ "/sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq"
const char *MQTT_HOST="broker.local"; int MQTT_PORT=1883;

static int read_temp_mC(void){
    FILE *f = fopen(TEMP_PATH, "r"); if(!f) return -1;
    int t; if(fscanf(f, "%d", &t)!=1){ fclose(f); return -1; }
    fclose(f); return t;
}
static int write_sysfs(const char *path, const char *val){
    FILE *f = fopen(path, "w"); if(!f) return -1;
    int rc = fprintf(f, "%s", val) < 0 ? -1 : 0; fclose(f); return rc;
}

int main(void){
    struct mosquitto *m;
    mosquitto_lib_init();
    m = mosquitto_new(NULL, true, NULL);
    if(mosquitto_connect(m, MQTT_HOST, MQTT_PORT, 60)) return 1;

    const int T_HIGH = 80000; /* 80 C in milliC */
    const int T_MED  = 70000; /* 70 C */
    const char *FREQ_HIGH = "1400000"; /* 1.4 GHz */
    const char *FREQ_MED  = "1000000";
    const char *FREQ_LOW  = "600000";

    while(1){
        int t = read_temp_mC();
        if(t<0) { sleep(5); continue; }
        const char *target = FREQ_HIGH;
        if(t >= T_HIGH) target = FREQ_LOW;
        else if(t >= T_MED) target = FREQ_MED;
        write_sysfs(SCALING_MAX_FREQ, target); /* throttle to protect device lifetime */
        char payload[128];
        snprintf(payload, sizeof(payload), "{\"temp_mC\":%d,\"max_freq\":%s}", t, target);
        mosquitto_publish(m, NULL, "edge/device/telemetry", strlen(payload), payload, 0, false);
        sleep(10); /* control interval tuned for stability and minimal write churn */
    }
    mosquitto_destroy(m); mosquitto_lib_cleanup(); return 0;
}