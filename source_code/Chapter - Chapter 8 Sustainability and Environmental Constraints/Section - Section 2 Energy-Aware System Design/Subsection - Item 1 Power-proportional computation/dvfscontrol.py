#!/usr/bin/env python3
# Adaptive DVFS: measure power, compute target freq, set cpufreq.
import time, glob, subprocess
from smbus2 import SMBus

INA219_ADDR = 0x40
I2C_BUS = 1
CPU_FREQ_PATHS = glob.glob('/sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_setspeed')

def read_ina219(bus):
    # Read shunt voltage & current registers; convert to watts externally.
    # Implementation depends on INA219 setup; this is placeholder conversion.
    # Use platform-specific drivers for production-grade accuracy.
    raw = bus.read_word_data(INA219_ADDR, 0x04)
    current_ma = (raw & 0xFF) << 8 | (raw >> 8)  # swap bytes
    voltage = 5.0  # read from ADC or fixed rail
    return (current_ma/1000.0) * voltage

def set_freq_all(freq):
    for p in CPU_FREQ_PATHS:
        try:
            with open(p, 'w') as f:
                f.write(str(freq))
        except PermissionError:
            subprocess.run(['sudo','chown','root:root',p])
            with open(p, 'w') as f:
                f.write(str(freq))

def available_freqs():
    p = CPU_FREQ_PATHS[0].replace('scaling_setspeed','scaling_available_frequencies')
    with open(p) as f:
        return sorted(map(int,f.read().split()))

def control_loop(target_deadline_s):
    freqs = available_freqs()
    bus = SMBus(I2C_BUS)
    while True:
        power_w = read_ina219(bus)
        # Simple heuristic: map power to freq; replace with Eq.(3) solver for f*
        # and clamp to meet deadline by profiling cycles-per-inference.
        # Here we pick a lower freq if power below threshold and deadline slack exists.
        if power_w < 2.0:
            target = freqs[0]  # conserve energy
        else:
            target = freqs[-1]  # prioritize performance
        set_freq_all(target)
        time.sleep(1.0)

if __name__ == '__main__':
    control_loop(target_deadline_s=0.05)