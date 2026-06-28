import geopandas as gpd
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
off_path = os.path.join(root_dir, "data", "official", "boundary.geojson")

print("Loading official dataset...")
off_gdf = gpd.read_file(off_path)

print(f"Total features: {len(off_gdf)}")
print("\nProvince distribution in official dataset (a04_tentinh):")
print(off_gdf['a04_tentinh'].value_counts(dropna=False))

print("\nFirst 10 rows properties:")
print(off_gdf.drop('geometry', axis=1).head(10))
