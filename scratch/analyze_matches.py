import geopandas as gpd
import json
import os
import sys

# Configure stdout for Unicode
sys.stdout.reconfigure(encoding='utf-8')

root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
osm_path = os.path.join(root_dir, "data", "osm", "boundary.geojson")
matches_path = os.path.join(root_dir, "output", "comparison", "compare_result.json")

print("Loading OSM boundary dataset...")
osm_gdf = gpd.read_file(osm_path)

print("Loading comparison results...")
with open(matches_path, "r", encoding="utf-8") as f:
    matches = json.load(f)

print(f"Total matched pairs: {len(matches)}")

level_counts = {}
mismatched_levels = []
mismatched_names_by_level = []

for m in matches:
    osm_id_val = int(m['osm_id'])
    rows = osm_gdf[osm_gdf['@id'] == osm_id_val]
    if rows.empty:
        rows = osm_gdf[osm_gdf['@id'] == str(osm_id_val)]
    if rows.empty:
        continue
    row = rows.iloc[0]
    lvl = str(row.get('admin_level'))
    level_counts[lvl] = level_counts.get(lvl, 0) + 1
    
    # Check if the matched OSM level is district (6) or province (4)
    if lvl in ['4', '6']:
        mismatched_levels.append({
            'official_id': m['official_id'],
            'official_name': m['official_name'],
            'province': m['province'],
            'osm_name': m['osm_name'],
            'osm_id': row.get('@id'),
            'admin_level': lvl,
            'overlap_ratio': m['overlap_ratio'],
            'iou': m['iou']
        })

print("\n--- OSM admin_level distribution in matches ---")
for lvl, count in sorted(level_counts.items()):
    print(f"Level {lvl}: {count} matches ({count/len(matches)*100:.2f}%)")

print(f"\nTotal mismatched matches (matched to OSM Level 4/6 instead of 8/9): {len(mismatched_levels)}")
if mismatched_levels:
    print("\nSample mismatched matches (first 10):")
    for item in mismatched_levels[:10]:
        print(f" - Official: {item['official_name']} ({item['province']}) matched to OSM: {item['osm_name']} (Level {item['admin_level']}, ID: {item['osm_id']}), Overlap: {item['overlap_ratio']*100:.1f}%, IoU: {item['iou']*100:.1f}%")
