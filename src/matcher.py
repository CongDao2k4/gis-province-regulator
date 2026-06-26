import os
import sys
import json
import logging
import re
import geopandas as gpd
from rapidfuzz import fuzz
from shapely.geometry import Polygon, MultiPolygon

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("matcher")

def clean_name(name: str) -> str:
    """Normalize and clean administrative names for better matching."""
    if not name:
        return ""
    # Convert to lowercase
    n = name.lower()
    
    # Remove accents/diacritics if necessary, but RapidFuzz is fine with accents.
    # Remove common prefix descriptors for communes/districts/provinces in Vietnam
    prefixes = [
        r"^xã\s+", r"^phường\s+", r"^thị\s*trấn\s+", r"^thị\s*xã\s+",
        r"^huyện\s+", r"^quận\s+", r"^thành\s*phố\s+", r"^tỉnh\s+"
    ]
    for pattern in prefixes:
        n = re.sub(pattern, "", n)
        
    # Standardize spaces and punctuation
    n = re.sub(r'[^\w\s]', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n

class BoundaryMatcher:
    """
    Matches Official boundaries to OSM boundaries using spatial index, names, 
    overlapping area, centroids, and area properties. 
    Does not use database or admin_level.
    """
    def __init__(self, off_gdf: gpd.GeoDataFrame, osm_gdf: gpd.GeoDataFrame):
        self.off_gdf = off_gdf.copy()
        self.osm_gdf = osm_gdf.copy()
        
    def match(self) -> list:
        logger.info("Starting Boundary Matching process...")
        
        # Ensure geometries are projected to a meter-based coordinate system for accurate area calculations
        # EPSG:3857 (Web Mercator) is suitable for local area calculations
        logger.info("Projecting geometries to EPSG:3857 for metric calculations...")
        off_proj = self.off_gdf.to_crs(epsg=3857)
        osm_proj = self.osm_gdf.to_crs(epsg=3857)
        
        # Ensure spatial index is built
        osm_sindex = osm_proj.sindex
        
        matches = []
        unmatched_official = []
        matched_osm_ids = set()
        
        # Determine column names based on dataset structures
        # Official: look for common ID and name fields
        off_id_col = 'a02_xa' if 'a02_xa' in off_proj.columns else (
            'id' if 'id' in off_proj.columns else None
        )
        off_name_col = 'a03_ten' if 'a03_ten' in off_proj.columns else (
            'name' if 'name' in off_proj.columns else None
        )
        off_prov_col = 'a04_tentinh' if 'a04_tentinh' in off_proj.columns else (
            'province' if 'province' in off_proj.columns else None
        )
        
        # OSM: look for common ID and name fields
        osm_id_col = 'id' if 'id' in osm_proj.columns else (
            'osm_id' if 'osm_id' in osm_proj.columns else None
        )
        osm_name_col = 'name' if 'name' in osm_proj.columns else None
        
        total_off = len(off_proj)
        logger.info(f"Matching {total_off} official boundaries against {len(osm_proj)} OSM boundaries...")
        
        # Convert OSM features to lists for rapid access
        osm_features = []
        for idx, row in osm_proj.iterrows():
            osm_features.append({
                'index': idx,
                'id': str(row[osm_id_col]) if osm_id_col else str(idx),
                'name': str(row[osm_name_col]) if (osm_name_col and osm_name_col in row and row[osm_name_col]) else "",
                'geometry': row['geometry'],
                'area': row['geometry'].area
            })
            
        for off_idx, off_row in off_proj.iterrows():
            off_id = str(off_row[off_id_col]) if off_id_col else str(off_idx)
            off_name = str(off_row[off_name_col]) if off_name_col and off_row[off_name_col] else ""
            off_prov = str(off_row[off_prov_col]) if off_prov_col and off_row[off_prov_col] else "N/A"
            off_geom = off_row['geometry']
            off_area = off_geom.area
            
            if off_geom is None or off_geom.is_empty:
                continue
                
            # Step 1: Query spatial index for bbox intersection
            possible_matches_idx = list(osm_sindex.intersection(off_geom.bounds))
            
            best_candidate = None
            best_score = -1.0
            
            # Step 2: Evaluate each overlapping candidate
            for idx in possible_matches_idx:
                osm_cand = osm_features[idx]
                osm_geom = osm_cand['geometry']
                
                # Check actual intersection
                if not off_geom.intersects(osm_geom):
                    continue
                    
                # Calculate metrics
                try:
                    intersection_geom = off_geom.intersection(osm_geom)
                    intersection_area = intersection_geom.area
                except Exception as e:
                    # Fallback for topology exceptions
                    logger.debug(f"Geometry intersection error for Official {off_name} and OSM {osm_cand['name']}: {e}")
                    continue
                    
                if intersection_area <= 0:
                    continue
                    
                # Calculate Union and IoU (Intersection over Union)
                union_area = off_area + osm_cand['area'] - intersection_area
                iou = intersection_area / max(union_area, 1e-9)
                
                # Overlap ratio (intersection over official area)
                overlap_ratio = intersection_area / max(off_area, 1e-9)
                
                # Name similarity (for details, not used for matching score)
                name_sim = fuzz.ratio(clean_name(off_name), clean_name(osm_cand['name'])) / 100.0
                
                # Centroid distance
                try:
                    centroid_dist = off_geom.centroid.distance(osm_geom.centroid)
                except Exception:
                    centroid_dist = 999999.0
                    
                # Combined score: purely spatial IoU
                score = iou
                
                if score > best_score:
                    best_score = score
                    best_candidate = {
                        'osm_id': osm_cand['id'],
                        'osm_name': osm_cand['name'],
                        'overlap_ratio': overlap_ratio,
                        'name_similarity': name_sim,
                        'centroid_dist': centroid_dist,
                        'score': score
                    }
            
            # Step 3: Classify match or add to unmatched
            if best_candidate and best_score >= 0.15:  # Require at least 15% IoU to filter out mismatched levels
                matches.append({
                    'official_id': off_id,
                    'official_name': off_name,
                    'province': off_prov,
                    'osm_id': best_candidate['osm_id'],
                    'osm_name': best_candidate['osm_name'],
                    'overlap_ratio': best_candidate['overlap_ratio'],
                    'name_similarity': best_candidate['name_similarity'],
                    'centroid_dist': best_candidate['centroid_dist'],
                    'score': best_candidate['score']
                })
                matched_osm_ids.add(best_candidate['osm_id'])
            else:
                unmatched_official.append({
                    'official_id': off_id,
                    'official_name': off_name,
                    'province': off_prov
                })
                
            if len(matches) % 1000 == 0 and len(matches) > 0:
                logger.info(f"Processed matches: {len(matches)}...")
                
        logger.info(f"Boundary matching finished. Matches found: {len(matches)}. Unmatched official: {len(unmatched_official)}")
        return matches

if __name__ == "__main__":
    import time
    from loader import GeoJSONLoader
    
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    osm_path = os.path.join(root_dir, "data", "osm", "boundary.geojson")
    off_path = os.path.join(root_dir, "data", "official", "boundary.geojson")
    
    print("=" * 60)
    print("BENCHMARK: BOUNDARY MATCHING PHASE")
    print("=" * 60)
    
    if os.path.exists(osm_path) and os.path.exists(off_path):
        # Load datasets
        print("Loading datasets...")
        osm_gdf = GeoJSONLoader(osm_path, "OSM").load()
        off_gdf = GeoJSONLoader(off_path, "Official").load()
        
        # Run Matcher
        print("Matching boundaries...")
        start = time.time()
        matcher = BoundaryMatcher(off_gdf, osm_gdf)
        matches = matcher.match()
        end = time.time()
        
        print(f"--> Matching phase completed in: {end - start:.2f} seconds")
        print(f"--> Total matches found: {len(matches)}")
        
        # Save intermediate matches.json for compare.py standalone run
        out_dir = os.path.join(root_dir, "output", "comparison")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "matches_temp.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(matches, f, ensure_ascii=False, indent=4)
        print(f"--> Saved intermediate matches to: {out_path}")
    else:
        print("Datasets not found. Please ensure both OSM and Official boundaries exist.")
        
    print("=" * 60)
