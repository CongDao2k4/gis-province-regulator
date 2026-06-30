import os
import sys
import time
import json
import logging

# Add project root to path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from src.tinh_loader import ProvinceLoader
from src.tinh_matcher import ProvinceMatcher
from src.tinh_compare import ProvinceGeometryComparer
from src.tinh_candidate import ProvinceCandidateGenerator
from src.tinh_stats import ProvinceStatisticsGenerator

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("tinh_pipeline")

def run_tinh_pipeline():
    logger.info("=" * 60)
    logger.info("STARTING PROVINCE & NATIONAL BOUNDARY REGULATOR PIPELINE")
    logger.info("=" * 60)
    
    start_total = time.time()
    
    # 1. Paths configuration
    off_path = os.path.join(ROOT_DIR, "data", "official", "provinces.geojson")
    osm_path = os.path.join(ROOT_DIR, "data", "osm", "tinh_boundary.geojson")
    
    output_comparison_dir = os.path.join(ROOT_DIR, "output", "tinh_comparison")
    output_candidate_dir = os.path.join(ROOT_DIR, "output", "tinh_candidates")
    output_statistics_dir = os.path.join(ROOT_DIR, "output", "tinh_statistics")
    
    # Check if OSM province file exists, if not raise warning
    if not os.path.exists(osm_path):
        logger.error(f"OSM boundary file not found at: {osm_path}. Please run scripts/02_extract_osm_tinh.sh first.")
        sys.exit(1)
        
    if not os.path.exists(off_path):
        logger.error(f"Official provinces file not found at: {off_path}.")
        sys.exit(1)
        
    # 2. Phase 1: Load Datasets
    logger.info("--- PHASE 1: LOADING DATASETS ---")
    start = time.time()
    off_loader = ProvinceLoader(off_path, "Official")
    osm_loader = ProvinceLoader(osm_path, "OSM")
    
    off_gdf = off_loader.load()
    osm_gdf = osm_loader.load()
    logger.info(f"Loaded datasets in {time.time() - start:.2f} seconds.")
    
    # 2.5. Phase 1.5: Simplify Boundaries for WebGIS
    logger.info("--- PHASE 1.5: SIMPLIFYING BOUNDARIES ---")
    simplified_dir = os.path.join(ROOT_DIR, "output", "simplified")
    os.makedirs(simplified_dir, exist_ok=True)
    try:
        # Simplify Official
        off_simple = off_gdf.copy()
        off_simple['geometry'] = off_simple['geometry'].simplify(0.001, preserve_topology=True)
        cols_off = ['geometry', 'id', 'a02_tinh', 'a01_ten']
        cols_off = [c for c in cols_off if c in off_simple.columns]
        off_simple = off_simple[cols_off]
        off_simple.to_file(os.path.join(simplified_dir, "tinh_official_communes.geojson"), driver="GeoJSON")
        logger.info("Exported simplified official provinces.")

        # Simplify OSM
        osm_simple = osm_gdf.copy()
        osm_simple['geometry'] = osm_simple['geometry'].simplify(0.001, preserve_topology=True)
        osm_id_col = '@id' if '@id' in osm_simple.columns else ('id' if 'id' in osm_simple.columns else 'osm_id')
        cols_osm = ['geometry', osm_id_col, 'name']
        cols_osm = [c for c in cols_osm if c in osm_simple.columns]
        osm_simple = osm_simple[cols_osm]
        osm_simple.to_file(os.path.join(simplified_dir, "tinh_osm_communes.geojson"), driver="GeoJSON")
        logger.info("Exported simplified OSM provinces.")
    except Exception as e:
        logger.error(f"Failed to simplify province boundaries: {e}")
    
    # 3. Phase 2: Boundary Matching
    logger.info("--- PHASE 2: BOUNDARY MATCHING ---")
    start = time.time()
    matcher = ProvinceMatcher(off_gdf, osm_gdf)
    matches = matcher.match()
    logger.info(f"Completed matching phase in {time.time() - start:.2f} seconds.")
    
    # Identify unmatched OSM features
    matched_osm_ids = {m['osm_id'] for m in matches}
    unmatched_osm = []
    
    osm_id_col = '@id' if '@id' in osm_gdf.columns else (
        'id' if 'id' in osm_gdf.columns else 'osm_id'
    )
    for _, row in osm_gdf.iterrows():
        osm_id = str(row[osm_id_col])
        if osm_id not in matched_osm_ids:
            unmatched_osm.append({
                'osm_id': osm_id,
                'name': row.get('name') or "N/A"
            })
            
    # Identify unmatched Official features
    matched_off_ids = {m['official_id'] for m in matches}
    unmatched_off = []
    off_id_col = 'a02_tinh' if 'a02_tinh' in off_gdf.columns else 'id'
    for _, row in off_gdf.iterrows():
        off_id = str(row[off_id_col])
        if off_id not in matched_off_ids:
            unmatched_off.append({
                'official_id': off_id,
                'official_name': row.get('a01_ten') or row.get('name') or "N/A"
            })
            
    # 4. Phase 3: Geometry Comparison & Differences
    logger.info("--- PHASE 3: GEOMETRY COMPARISON ---")
    start = time.time()
    comparer = ProvinceGeometryComparer(matches, off_gdf, osm_gdf)
    missing_count, new_count = comparer.compare(output_comparison_dir)
    logger.info(f"Completed geometry comparison in {time.time() - start:.2f} seconds.")
    
    # 5. Phase 4: Candidate Categorization
    logger.info("--- PHASE 4: CANDIDATE CATEGORIZATION ---")
    start = time.time()
    cand_gen = ProvinceCandidateGenerator(matches, unmatched_off, unmatched_osm, off_gdf)
    candidates = cand_gen.generate(output_candidate_dir)
    logger.info(f"Completed candidate categorization in {time.time() - start:.2f} seconds.")
    
    # 6. Phase 5: Statistics & Reports
    logger.info("--- PHASE 5: STATISTICS & REPORTS ---")
    start = time.time()
    with open(os.path.join(output_comparison_dir, "compare_result.json"), "r", encoding="utf-8") as f:
        compare_results = json.load(f)
    stats_gen = ProvinceStatisticsGenerator(compare_results, missing_count, new_count)
    stats = stats_gen.generate(output_statistics_dir)
    logger.info(f"Completed statistics and reports in {time.time() - start:.2f} seconds.")
    
    logger.info("=" * 60)
    logger.info(f"PIPELINE COMPLETED SUCCESSFULLY IN {time.time() - start_total:.2f} SECONDS.")
    logger.info("=" * 60)

if __name__ == "__main__":
    run_tinh_pipeline()
