import os
import sys
import geopandas as gpd
import json

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
osm_path = os.path.join(root_dir, "data", "osm", "boundary.geojson")
off_path = os.path.join(root_dir, "data", "official", "boundary.geojson")

print("Loading OSM...")
osm_gdf = gpd.read_file(osm_path)
print("Loading Official...")
off_gdf = gpd.read_file(off_path)

# Test with first pair in compare_result.json
compare_res_path = os.path.join(root_dir, "output", "data", "compare_result.json")
with open(compare_res_path, "r", encoding="utf-8") as f:
    results = json.load(f)

first = results[0]
off_id = first["official_id"]
osm_id = first["osm_id"]

print(f"Testing pair: off_id={off_id}, osm_id={osm_id}")

off_geom = off_gdf[off_gdf['a02_xa'] == off_id].iloc[0]['geometry'] if 'a02_xa' in off_gdf.columns else off_gdf.iloc[0]['geometry']
osm_geom = osm_gdf[osm_gdf['id'] == osm_id].iloc[0]['geometry'] if 'id' in osm_gdf.columns else osm_gdf.iloc[0]['geometry']

print("Geometries loaded.")
try:
    print("Validating geometries...")
    off_geom = off_geom.make_valid()
    osm_geom = osm_geom.make_valid()
    print("Computing difference...")
    osm_only = osm_geom.difference(off_geom)
    print("osm_only computed.")
    off_only = off_geom.difference(osm_geom)
    print("off_only computed.")
    overlap_geom = off_geom.intersection(osm_geom)
    print("overlap_geom computed.")
    print(f"osm_only: {osm_only.is_empty}, off_only: {off_only.is_empty}, overlap: {overlap_geom.is_empty}")
except Exception as e:
    print(f"ERROR: {e}")
