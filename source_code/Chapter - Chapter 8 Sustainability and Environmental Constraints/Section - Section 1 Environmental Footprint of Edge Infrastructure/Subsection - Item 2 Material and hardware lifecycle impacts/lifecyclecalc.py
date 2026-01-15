#!/usr/bin/env python3
"""
lifecycle_calc.py - production-ready lifecycle CO2e calculator.

Input: BOM JSON with components: [{ "name":..., "mass_kg":..., "mat_emf":..., 
  "proc_emf":..., "transport_kgco2":... }, ...]
Optional: --grid g (kgCO2e/kWh), --annual-energy kWh
Output: JSON summary with annualized and component contributions.
"""
from typing import List, Dict
import json, argparse, math

def load_bom(path: str) -> List[Dict]:
    with open(path, 'r', encoding='utf8') as f:
        return json.load(f)

def component_embodied(c: Dict) -> float:
    # mass_kg * material emission factor + process + transport
    return c.get('mass_kg',0.0) * c.get('mat_emf',0.0) + c.get('proc_emf',0.0) + c.get('transport_kgco2',0.0)

def compute(bom: List[Dict], lifetime_yr: float, recycle_credit: float,
            grid_emf: float, annual_energy_kwh: float) -> Dict:
    emb_list = [component_embodied(c) for c in bom]
    total_emb = sum(emb_list)
    annual_op = grid_emf * annual_energy_kwh
    annualized_emb = (total_emb - recycle_credit) / max(lifetime_yr, 0.1)
    return {
        'total_embodied_kgco2e': round(total_emb,4),
        'annual_operational_kgco2e': round(annual_op,4),
        'annualized_embodied_kgco2e': round(annualized_emb,4),
        'annual_total_kgco2e': round(annualized_emb + annual_op,4)
    }

def main():
    p = argparse.ArgumentParser(description='Lifecycle CO2e calculator')
    p.add_argument('bom', help='BOM JSON path')
    p.add_argument('--lifetime', type=float, default=5.0, help='device lifetime in years')
    p.add_argument('--recycle', type=float, default=0.0, help='recovery credit kgCO2e')
    p.add_argument('--grid', type=float, default=0.4, help='grid kgCO2e per kWh')
    p.add_argument('--annual-energy', type=float, default=50.0, help='annual device energy kWh')
    args = p.parse_args()
    bom = load_bom(args.bom)
    out = compute(bom, args.lifetime, args.recycle, args.grid, args.annual_energy)
    print(json.dumps(out, indent=2))

if __name__ == '__main__':
    main()