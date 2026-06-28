import os
import sys
import json
import logging
import geopandas as gpd
import pandas as pd
from shapely.ops import orient
from shapely.geometry import mapping, shape
from shapely.validation import make_valid

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("compare")

class GeometryComparer:
    """
    Computes precise geometric metrics for matched boundaries:
    - Overlap (IoU & overlap ratio)
    - Hausdorff distance
    - Area Difference
    - Boundary Difference
    Generates difference.geojson, missing.geojson, new.geojson, and compare_result.json.
    """
    def __init__(self, off_gdf: gpd.GeoDataFrame, osm_gdf: gpd.GeoDataFrame, matches: list):
        self.off_gdf = off_gdf
        self.osm_gdf = osm_gdf
        self.matches = matches

    def run_compare(self, output_dir: str):
        logger.info("Starting Geometry Comparison...")
        os.makedirs(output_dir, exist_ok=True)
        
        # Build dictionaries of geometries for fast lookup
        # Project both to EPSG:32648 (UTM Zone 48N) for metric calculations
        logger.info("Projecting datasets to EPSG:32648 for metric calculations...")
        off_proj = self.off_gdf.to_crs(epsg=32648)
        osm_proj = self.osm_gdf.to_crs(epsg=32648)
        
        # Build lookup tables
        off_id_col = 'a02_xa' if 'a02_xa' in off_proj.columns else (
            'id' if 'id' in off_proj.columns else None
        )
        off_name_col = 'a03_ten' if 'a03_ten' in off_proj.columns else (
            'name' if 'name' in off_proj.columns else None
        )
        
        osm_id_col = '@id' if '@id' in osm_proj.columns else (
            'id' if 'id' in osm_proj.columns else (
                'osm_id' if 'osm_id' in osm_proj.columns else None
            )
        )
        osm_name_col = 'name' if 'name' in osm_proj.columns else None
        
        off_dict = {}
        for idx, row in off_proj.iterrows():
            off_id = str(row[off_id_col]) if off_id_col else str(idx)
            off_dict[off_id] = row
            
        osm_dict = {}
        for idx, row in osm_proj.iterrows():
            osm_id = str(row[osm_id_col]) if osm_id_col else str(idx)
            osm_dict[osm_id] = row

        # Also keep 4326 geometries for export
        off_4326_dict = {}
        for idx, row in self.off_gdf.to_crs(epsg=4326).iterrows():
            off_id = str(row[off_id_col]) if off_id_col else str(idx)
            off_4326_dict[off_id] = row['geometry']
            
        osm_4326_dict = {}
        for idx, row in self.osm_gdf.to_crs(epsg=4326).iterrows():
            osm_id = str(row[osm_id_col]) if osm_id_col else str(idx)
            osm_4326_dict[osm_id] = row['geometry']

        compare_results = []
        diff_features = []
        matched_off_ids = set()
        matched_osm_ids = set()

        total_matches = len(self.matches)
        logger.info(f"Comparing {total_matches} matched pairs...")
        
        for idx, m in enumerate(self.matches):
            off_id = str(m['official_id'])
            osm_id = str(m['osm_id'])
            
            matched_off_ids.add(off_id)
            matched_osm_ids.add(osm_id)
            
            off_row = off_dict.get(off_id)
            osm_row = osm_dict.get(osm_id)
            
            if off_row is None or osm_row is None:
                continue
                
            off_geom = off_row['geometry']
            osm_geom = osm_row['geometry']
            
            off_geom_4326 = off_4326_dict.get(off_id)
            osm_geom_4326 = osm_4326_dict.get(osm_id)
            
            # Compute metric-based variables
            area_off = off_geom.area
            area_osm = osm_geom.area
            area_diff = abs(area_off - area_osm)
            
            try:
                intersection_geom = off_geom.intersection(osm_geom)
                intersect_area = intersection_geom.area
                union_geom = off_geom.union(osm_geom)
                union_area = union_geom.area
                iou = intersect_area / max(union_area, 1e-9)
            except Exception:
                intersect_area = 0.0
                union_area = area_off + area_osm
                iou = 0.0
            
            # Hausdorff distance (simplify geometries to 10m to speed up computation)
            try:
                hausdorff = off_geom.simplify(10.0, preserve_topology=True).hausdorff_distance(
                    osm_geom.simplify(10.0, preserve_topology=True)
                )
            except Exception:
                hausdorff = -1.0
                
            overlap_ratio = intersect_area / max(area_off, 1e-9)
            
            result_item = {
                "official_id": off_id,
                "official_name": m['official_name'],
                "province": m['province'],
                "osm_id": osm_id,
                "osm_name": m['osm_name'],
                "area_official_sqm": area_off,
                "area_osm_sqm": area_osm,
                "area_difference_sqm": area_diff,
                "intersect_area_sqm": intersect_area,
                "overlap_ratio": overlap_ratio,
                "iou": iou,
                "hausdorff": hausdorff,
                "name_similarity": m['name_similarity']
            }
            compare_results.append(result_item)
            
            # Compute difference geometries in 4326 for mapping/rendering
            if off_geom_4326 is not None and osm_geom_4326 is not None:
                try:
                    # Clean/fix and simplify geometries (to 10m/0.0001 deg) to optimize differences speed
                    off_geom_4326 = make_valid(off_geom_4326).simplify(0.0001, preserve_topology=True)
                    osm_geom_4326 = make_valid(osm_geom_4326).simplify(0.0001, preserve_topology=True)
                    
                    # Compute spatial differences
                    osm_only = osm_geom_4326.difference(off_geom_4326)
                    off_only = off_geom_4326.difference(osm_geom_4326)
                    overlap_geom = off_geom_4326.intersection(osm_geom_4326)
                    
                    is_purple = overlap_ratio < 0.8
                    
                    def add_diff_feature(geom, color, category):
                        if geom is not None and not geom.is_empty:
                            diff_features.append({
                                "type": "Feature",
                                "geometry": geom.__geo_interface__,
                                "properties": {
                                    "official_id": off_id,
                                    "osm_id": osm_id,
                                    "a03_ten": m['official_name'],
                                    "osm_name": m['osm_name'],
                                    "fillColor": color,
                                    "category": category,
                                    "overlap_ratio": overlap_ratio,
                                    "iou": iou
                                }
                            })
                            
                    if is_purple:
                        add_diff_feature(off_only, "purple", "Geometry Changed")
                        add_diff_feature(osm_only, "purple", "Geometry Changed")
                    else:
                        add_diff_feature(osm_only, "red", "Only in OSM")
                        add_diff_feature(off_only, "blue", "Only in Official")
                        add_diff_feature(overlap_geom, "yellow", "Overlap")
                        
                except Exception as e:
                    logger.debug(f"Failed to generate difference polygons for match {off_id}: {e}")

            if (idx + 1) % 2000 == 0:
                logger.info(f"Compared {idx + 1} matches...")

        # Save compare results
        logger.info("Saving comparison outputs...")
        with open(os.path.join(output_dir, "compare_result.json"), "w", encoding="utf-8") as f:
            json.dump(compare_results, f, ensure_ascii=False, indent=4)
            
        with open(os.path.join(output_dir, "difference.geojson"), "w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "features": diff_features}, f, ensure_ascii=False)

        # Generate missing.geojson (Official polygons that are NOT matched)
        missing_features = []
        for idx, row in self.off_gdf.to_crs(epsg=4326).iterrows():
            off_id = str(row[off_id_col]) if off_id_col else str(idx)
            if off_id not in matched_off_ids:
                geom = row['geometry']
                if geom is not None and not geom.is_empty:
                    missing_features.append({
                        "type": "Feature",
                        "geometry": geom.__geo_interface__,
                        "properties": {
                            "official_id": off_id,
                            "official_name": str(row[off_name_col]) if (off_name_col and off_name_col in row and row[off_name_col]) else "",
                            "province": str(row['a04_tentinh']) if 'a04_tentinh' in row else "N/A",
                            "category": "Missing in OSM"
                        }
                    })
        with open(os.path.join(output_dir, "missing.geojson"), "w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "features": missing_features}, f, ensure_ascii=False)

        # Generate new.geojson (OSM polygons that are NOT matched)
        new_features = []
        for idx, row in self.osm_gdf.to_crs(epsg=4326).iterrows():
            osm_id = str(row[osm_id_col]) if osm_id_col else str(idx)
            if osm_id not in matched_osm_ids:
                geom = row['geometry']
                if geom is not None and not geom.is_empty:
                    new_features.append({
                        "type": "Feature",
                        "geometry": geom.__geo_interface__,
                        "properties": {
                            "osm_id": osm_id,
                            "osm_name": str(row[osm_name_col]) if (osm_name_col and osm_name_col in row and row[osm_name_col]) else "",
                            "category": "New in OSM"
                        }
                    })
        with open(os.path.join(output_dir, "new.geojson"), "w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "features": new_features}, f, ensure_ascii=False)

        logger.info(f"Geometry compare complete. Saved difference, missing ({len(missing_features)}), and new ({len(new_features)}) to {output_dir}")
        return compare_results

if __name__ == "__main__":
    import time
    from loader import GeoJSONLoader
    
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    osm_path = os.path.join(root_dir, "data", "osm", "boundary.geojson")
    off_path = os.path.join(root_dir, "data", "official", "boundary.geojson")
    matches_path = os.path.join(root_dir, "output", "comparison", "matches_temp.json")
    
    print("=" * 60)
    print("BENCHMARK: GEOMETRY COMPARISON PHASE")
    print("=" * 60)
    
    if os.path.exists(osm_path) and os.path.exists(off_path) and os.path.exists(matches_path):
        # Load datasets
        print("Loading datasets...")
        osm_gdf = GeoJSONLoader(osm_path, "OSM").load()
        off_gdf = GeoJSONLoader(off_path, "Official").load()
        
        # Load intermediate matches
        print(f"Loading matches from: {matches_path}")
        with open(matches_path, "r", encoding="utf-8") as f:
            matches = json.load(f)
            
        # Run Comparer
        print("Comparing geometries...")
        start = time.time()
        comparer = GeometryComparer(off_gdf, osm_gdf, matches)
        out_dir = os.path.join(root_dir, "output", "comparison")
        compare_results = comparer.run_compare(out_dir)
        end = time.time()
        
        print(f"--> Comparison phase completed in: {end - start:.2f} seconds")
    else:
        print("Required datasets or intermediate matches_temp.json not found.")
        print("Please run loader.py and matcher.py first.")
        
    print("=" * 60)
