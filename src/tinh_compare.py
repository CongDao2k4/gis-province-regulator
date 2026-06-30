import os
import sys
import json
import logging
import geopandas as gpd
from shapely.geometry import shape, mapping
from shapely.ops import unary_union
from src.loader import GeoJSONLoader
from src.compare import make_valid

# Add project root to path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("tinh_compare")

class ProvinceGeometryComparer:
    """
    Compares geometries of matched Province/National boundaries.
    Generates difference features (red = excess OSM, purple = missing on OSM).
    """
    def __init__(self, matches: list, off_gdf: gpd.GeoDataFrame, osm_gdf: gpd.GeoDataFrame):
        self.matches = matches
        self.off_gdf = off_gdf
        self.osm_gdf = osm_gdf
        
    def compare(self, output_dir: str):
        logger.info("Starting Province Geometry Comparison...")
        os.makedirs(output_dir, exist_ok=True)
        
        # Project datasets to EPSG:32648
        off_proj = self.off_gdf.to_crs(epsg=32648)
        osm_proj = self.osm_gdf.to_crs(epsg=32648)
        
        # Indexes for fast lookup
        off_id_col = 'a02_tinh' if 'a02_tinh' in off_proj.columns else 'id'
        osm_id_col = '@id' if '@id' in osm_proj.columns else (
            'id' if 'id' in osm_proj.columns else 'osm_id'
        )
        
        off_dict = {str(row[off_id_col]): row for _, row in off_proj.iterrows()}
        osm_dict = {str(row[osm_id_col]): row for _, row in osm_proj.iterrows()}
        
        # Raw datasets in WGS84 for GeoJSON output
        off_raw_dict = {str(row[off_id_col]): row for _, row in self.off_gdf.iterrows()}
        osm_raw_dict = {str(row[osm_id_col]): row for _, row in self.osm_gdf.iterrows()}
        
        compare_results = []
        diff_features = []
        matched_osm_ids = set()
        matched_off_ids = set()
        
        for idx, m in enumerate(self.matches):
            off_id = m['official_id']
            osm_id = m['osm_id']
            overlap_ratio = m['overlap_ratio']
            name_similarity = m['name_similarity']
            
            matched_off_ids.add(off_id)
            matched_osm_ids.add(osm_id)
            
            off_row = off_dict.get(off_id)
            osm_row = osm_dict.get(osm_id)
            
            if off_row is None or osm_row is None:
                continue
                
            off_geom = off_row['geometry']
            osm_geom = osm_row['geometry']
            
            # Area calculations (m2)
            off_area = off_geom.area
            osm_area = osm_geom.area
            
            # Calculate intersection
            try:
                intersection_geom = off_geom.intersection(osm_geom)
                intersection_area = intersection_geom.area
            except Exception:
                intersection_area = 0.0
                
            union_area = off_area + osm_area - intersection_area
            iou = intersection_area / max(union_area, 1e-9)
            area_difference = abs(off_area - osm_area)
            
            # Calculate Hausdorff distance (metric)
            try:
                hausdorff = off_geom.simplify(10.0, preserve_topology=True).hausdorff_distance(
                    osm_geom.simplify(10.0, preserve_topology=True)
                )
            except Exception:
                hausdorff = -1.0
            
            compare_results.append({
                "official_id": off_id,
                "official_name": m['official_name'],
                "province": m['province'],
                "osm_id": osm_id,
                "osm_name": m['osm_name'],
                "overlap_ratio": overlap_ratio,
                "name_similarity": name_similarity,
                "iou": iou,
                "area_difference_sqm": area_difference,
                "hausdorff": hausdorff
            })
            
            # Generate difference shapes in WGS84
            off_raw = off_raw_dict.get(off_id)
            osm_raw = osm_raw_dict.get(osm_id)
            
            if off_raw is not None and osm_raw is not None:
                try:
                    off_geom_4326 = make_valid(off_raw['geometry'])
                    osm_geom_4326 = make_valid(osm_raw['geometry'])
                    
                    # Compute spatial differences
                    osm_only = osm_geom_4326.difference(off_geom_4326)
                    off_only = off_geom_4326.difference(osm_geom_4326)
                    
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
                        add_diff_feature(off_only, "purple", "Only in Official") # Use purple for missing OSM
                        
                except Exception as e:
                    logger.debug(f"Failed to generate difference polygons for match {off_id}: {e}")
                    
        # Save compare results
        logger.info("Saving comparison outputs...")
        with open(os.path.join(output_dir, "compare_result.json"), "w", encoding="utf-8") as f:
            json.dump(compare_results, f, ensure_ascii=False, indent=4)
            
        with open(os.path.join(output_dir, "difference.geojson"), "w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "features": diff_features}, f, ensure_ascii=False)
            
        # Generate missing.geojson (Official polygons that are NOT matched)
        missing_features = []
        for off_id, row in off_raw_dict.items():
            if off_id not in matched_off_ids:
                missing_features.append({
                    "type": "Feature",
                    "geometry": row['geometry'].__geo_interface__,
                    "properties": {
                        "a02_xa": off_id, # Keep compatibility with frontend properties keys
                        "a02_tinh": off_id,
                        "a03_ten": row.get('a01_ten') or row.get('name') or "N/A",
                        "a04_tentinh": row.get('a01_ten') or "N/A"
                    }
                })
        with open(os.path.join(output_dir, "missing.geojson"), "w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "features": missing_features}, f, ensure_ascii=False)
            
        # Generate new.geojson (OSM polygons that are NOT matched)
        new_features = []
        for osm_id, row in osm_raw_dict.items():
            if osm_id not in matched_osm_ids:
                new_features.append({
                    "type": "Feature",
                    "geometry": row['geometry'].__geo_interface__,
                    "properties": {
                        "osm_id": osm_id,
                        "name": row.get('name') or "N/A"
                    }
                })
        with open(os.path.join(output_dir, "new.geojson"), "w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "features": new_features}, f, ensure_ascii=False)
            
        logger.info("Province geometry comparison completed successfully.")
        return len(missing_features), len(new_features)
