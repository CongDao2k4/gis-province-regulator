import os
import sys
import json
import logging
import re
import geopandas as gpd
from rapidfuzz import fuzz

# Add project root to path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from src.matcher import clean_name

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("tinh_matcher")

class ProvinceMatcher:
    """
    Matches Official Province/National boundaries to OSM boundaries.
    """
    def __init__(self, off_gdf: gpd.GeoDataFrame, osm_gdf: gpd.GeoDataFrame):
        self.off_gdf = off_gdf.copy()
        self.osm_gdf = osm_gdf.copy()
        
    def match(self) -> list:
        logger.info("Starting Province/National Boundary Matching...")
        
        # Project to EPSG:32648 for accurate area calculations
        off_proj = self.off_gdf.to_crs(epsg=32648)
        osm_proj = self.osm_gdf.to_crs(epsg=32648)
        
        osm_sindex = osm_proj.sindex
        
        matches = []
        unmatched_official = []
        matched_osm_ids = set()
        
        # Official: columns for provinces
        off_id_col = 'a02_tinh' if 'a02_tinh' in off_proj.columns else (
            'id' if 'id' in off_proj.columns else None
        )
        off_name_col = 'a01_ten' if 'a01_ten' in off_proj.columns else None
        
        # OSM: columns
        osm_id_col = '@id' if '@id' in osm_proj.columns else (
            'id' if 'id' in osm_proj.columns else (
                'osm_id' if 'osm_id' in osm_proj.columns else None
            )
        )
        osm_name_col = 'name' if 'name' in osm_proj.columns else None
        
        # Convert OSM features to list
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
            off_geom = off_row['geometry']
            off_area = off_geom.area
            
            if off_geom is None or off_geom.is_empty:
                continue
                
            # Query spatial index
            possible_matches_idx = list(osm_sindex.intersection(off_geom.bounds))
            
            best_candidate = None
            best_score = -1.0
            
            for idx in possible_matches_idx:
                osm_cand = osm_features[idx]
                osm_geom = osm_cand['geometry']
                
                if not off_geom.intersects(osm_geom):
                    continue
                    
                try:
                    intersection_geom = off_geom.intersection(osm_geom)
                    intersection_area = intersection_geom.area
                except Exception:
                    continue
                    
                if intersection_area <= 0:
                    continue
                    
                union_area = off_area + osm_cand['area'] - intersection_area
                iou = intersection_area / max(union_area, 1e-9)
                overlap_ratio = intersection_area / max(off_area, 1e-9)
                name_sim = fuzz.ratio(clean_name(off_name), clean_name(osm_cand['name'])) / 100.0
                
                try:
                    centroid_dist = off_geom.centroid.distance(osm_geom.centroid)
                except Exception:
                    centroid_dist = 999999.0
                    
                # Combined score: IoU is used as standard metric
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
                    
            # Classification
            is_valid_match = True
            if best_candidate:
                # Reject matches with very low similarity and IoU
                if best_candidate['name_similarity'] < 0.35 and best_candidate['score'] < 0.40:
                    is_valid_match = False
            
            if best_candidate and best_score >= 0.15 and is_valid_match:
                matches.append({
                    'official_id': off_id,
                    'official_name': off_name,
                    'province': off_name, # Province name itself
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
                    'province': off_name
                })
                
        logger.info(f"Province matching finished. Matches: {len(matches)}. Unmatched: {len(unmatched_official)}")
        return matches
