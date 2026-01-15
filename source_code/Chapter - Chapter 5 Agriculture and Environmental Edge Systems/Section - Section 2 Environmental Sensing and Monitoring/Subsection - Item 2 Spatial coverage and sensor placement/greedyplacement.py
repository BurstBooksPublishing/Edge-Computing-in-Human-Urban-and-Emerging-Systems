# Greedy coverage placement. Requires geopandas, shapely, numpy.
import geopandas as gpd
from shapely.geometry import Point
import numpy as np
import json

def generate_candidates(polygon, spacing):
    minx, miny, maxx, maxy = polygon.bounds
    xs = np.arange(minx, maxx + spacing, spacing)
    ys = np.arange(miny, maxy + spacing, spacing)
    pts = [Point(x, y) for x in xs for y in ys if polygon.contains(Point(x, y))]
    return pts

def greedy_place(polygon, r, spacing, budget=None, target_coverage=0.95):
    candidates = generate_candidates(polygon, spacing)
    footprints = [c.buffer(r) for c in candidates]
    uncovered = polygon
    selected = []
    total_area = polygon.area
    covered_area = 0.0
    while (budget is None or len(selected) < budget) and covered_area/total_area < target_coverage:
        gains = [(i, (footprints[i] & uncovered).area) for i in range(len(candidates))]
        i_max, gain = max(gains, key=lambda x: x[1])
        if gain <= 0:
            break
        selected.append(candidates[i_max])
        uncovered = uncovered.difference(footprints[i_max])
        covered_area = total_area - uncovered.area
        # remove selected candidate
        candidates.pop(i_max)
        footprints.pop(i_max)
    # produce GeoJSON and simple MQTT provisioning
    gdf = gpd.GeoDataFrame(geometry=selected, crs="EPSG:3857")
    provisioning = []
    for idx, row in gdf.iterrows():
        dev = {
            "device_id": f"sensor-{idx:04d}",
            "sensing_radius_m": r,
            "provision": {
                "transport": "lorawan",
                "join_eui": "REPLACE_ME",
                "app_key": "REPLACE_ME"
            },
            "mqtt": {"topic": f"edge/agri/sensor/{idx:04d}/telemetry"}
        }
        provisioning.append(dev)
    return gdf, provisioning

# Example usage: load polygon (projected CRS), place sensors, export.
# field = gpd.read_file("field_polygon.geojson").to_crs(epsg=3857).geometry[0]
# gdf, prov = greedy_place(field, r=50.0, spacing=40.0, budget=400)
# gdf.to_file("placements.geojson", driver="GeoJSON")
# with open("provisioning.json","w") as f: json.dump(prov, f, indent=2)