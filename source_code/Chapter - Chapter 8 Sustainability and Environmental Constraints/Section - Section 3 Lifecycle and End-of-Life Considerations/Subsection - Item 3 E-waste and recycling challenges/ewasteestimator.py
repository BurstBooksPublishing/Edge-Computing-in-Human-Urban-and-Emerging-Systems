#!/usr/bin/env python3
"""Compute annual e-waste flux and savings from refurbishment policies."""
from typing import List, Dict
import numpy as np
import pandas as pd

def fleet_flux(devices: List[Dict], refurb_rate: float=0.0) -> pd.DataFrame:
    """
    devices: list of dicts with keys 'model','deploy_rate','mass_kg','mean_life_yr'
    refurb_rate: fraction [0,1] of retired units refurbished and redeployed
    returns DataFrame with columns ['model','annual_flux_kg','saved_kg']
    """
    rows = []
    for d in devices:
        r = float(d['deploy_rate'])
        m = float(d['mass_kg'])
        # Annual generation equals deployments * mass (steady-state)
        annual_flux = r * m
        saved = refurb_rate * annual_flux
        rows.append({'model': d['model'],
                     'annual_flux_kg': annual_flux,
                     'saved_kg': saved,
                     'net_flux_kg': annual_flux - saved})
    return pd.DataFrame(rows)

if __name__ == "__main__":
    # Example fleet: street sensors, Jetson micro-servers, gateway nodes
    fleet = [
        {'model': 'street_cam_v2', 'deploy_rate': 1200, 'mass_kg': 2.5, 'mean_life_yr': 5},
        {'model': 'edge_gateway_x1','deploy_rate': 200, 'mass_kg': 6.0, 'mean_life_yr': 7},
        {'model': 'micro_server_jetson','deploy_rate': 50, 'mass_kg': 9.0, 'mean_life_yr': 4},
    ]
    df = fleet_flux(fleet, refurb_rate=0.35)  # 35% refurbishment
    print(df.to_string(index=False))