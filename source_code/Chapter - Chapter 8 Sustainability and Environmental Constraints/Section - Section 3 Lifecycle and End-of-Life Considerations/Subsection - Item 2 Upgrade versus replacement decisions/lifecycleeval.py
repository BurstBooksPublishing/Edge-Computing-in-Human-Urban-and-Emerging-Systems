from dataclasses import dataclass
from typing import Callable
import math

@dataclass
class DeviceSpec:
    capex: float              # purchase or upgrade cost ($)
    energy_per_inference: float  # joules per inference
    embodied_carbon: float    # kg CO2e
    maintenance_rate: float   # $ per year
    lifetime_years: float

def npv(device: DeviceSpec, rate: float, inf_per_sec: float, hours_per_year: float, energy_price_per_joule: float, carbon_price_per_kg: float, horizon_years: float) -> float:
    # compute yearly energy cost
    yearly_infs = inf_per_sec * hours_per_year * 3600.0
    yearly_energy_joules = device.energy_per_inference * yearly_infs
    yearly_energy_cost = yearly_energy_joules * energy_price_per_joule
    # annual costs vectorized analytically assuming constant yearly costs
    npv_operational = 0.0
    for y in range(1, int(horizon_years)+1):
        discount = (1.0 + rate) ** y
        npv_operational += (yearly_energy_cost + device.maintenance_rate) / discount
    # add capex and embodied carbon cost at t=0
    npv_total = device.capex + npv_operational + device.embodied_carbon * carbon_price_per_kg
    return npv_total

# Example usage (values illustrative)
old = DeviceSpec(capex=0.0, energy_per_inference=5.0, embodied_carbon=20.0, maintenance_rate=50.0, lifetime_years=5.0)
upgrade = DeviceSpec(capex=120.0, energy_per_inference=4.0, embodied_carbon=5.0, maintenance_rate=40.0, lifetime_years=3.0)
replace = DeviceSpec(capex=400.0, energy_per_inference=1.2, embodied_carbon=40.0, maintenance_rate=30.0, lifetime_years=7.0)

decision_metrics = {
    'old': npv(old, rate=0.07, inf_per_sec=30.0, hours_per_year=24*365, energy_price_per_joule=0.00000028, carbon_price_per_kg=0.1, horizon_years=5),
    'upgrade': npv(upgrade, rate=0.07, inf_per_sec=30.0, hours_per_year=24*365, energy_price_per_joule=0.00000028, carbon_price_per_kg=0.1, horizon_years=5),
    'replace': npv(replace, rate=0.07, inf_per_sec=30.0, hours_per_year=24*365, energy_price_per_joule=0.00000028, carbon_price_per_kg=0.1, horizon_years=5),
}
# choose minimal NPV
best = min(decision_metrics, key=decision_metrics.get)
print("Best lifecycle action:", best, "NPV:", decision_metrics[best])