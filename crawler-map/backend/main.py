import os
import sys
import json
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("main")

app = FastAPI(title="Crawler Map WebGIS API")

# Root directory of the project
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from scripts.apply_osm_edit import apply_edit, clean_name
from scripts.apply_tinh_edit import apply_edit as apply_tinh_edit
from src.tinh_loader import ProvinceLoader
from shapely.geometry import mapping

OUTPUT_DIR = os.path.join(ROOT_DIR, "output")

# Mount output folder as a static folder to serve charts (e.g. /static/statistics/...)
app.mount("/static", StaticFiles(directory=OUTPUT_DIR), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def load_geojson(subfolder: str, filename: str):
    path = os.path.join(OUTPUT_DIR, subfolder, filename)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading GeoJSON {subfolder}/{filename}: {e}")
            return {"type": "FeatureCollection", "features": []}
    logger.warning(f"File not found: {path}")
    return {"type": "FeatureCollection", "features": []}

# Pre-load datasets at startup for fast O(1) lookups
logger.info("Pre-loading simplified boundary datasets into memory for fast lookup...")

# Caches for Provinces & National Boundary
TINH_OFFICIAL_DICT = {}
TINH_OSM_DICT = {}
TINH_DIFF_DICT = {}

def reload_tinh_cache():
    global TINH_OFFICIAL_DICT, TINH_OSM_DICT, TINH_DIFF_DICT
    TINH_OFFICIAL_DICT.clear()
    TINH_OSM_DICT.clear()
    TINH_DIFF_DICT.clear()
    
    off_path = os.path.join(ROOT_DIR, "data", "official", "provinces.geojson")
    if os.path.exists(off_path):
        try:
            loader = ProvinceLoader(off_path, "Official")
            gdf = loader.load()
            for _, row in gdf.iterrows():
                fid = str(row['a02_tinh'])
                feat = {
                    "type": "Feature",
                    "id": fid,
                    "geometry": mapping(row['geometry']),
                    "properties": {
                        "a02_tinh": fid,
                        "a01_ten": str(row['a01_ten']),
                        "id": str(row['id'])
                    }
                }
                TINH_OFFICIAL_DICT[fid] = feat
            logger.info(f"Successfully cached {len(TINH_OFFICIAL_DICT)} official provinces.")
        except Exception as e:
            logger.error(f"Failed to load official provinces cache: {e}")
            
    osm_path = os.path.join(ROOT_DIR, "data", "osm", "tinh_boundary.geojson")
    if os.path.exists(osm_path):
        try:
            with open(osm_path, "r", encoding="utf-8") as f:
                osm_data = json.load(f)
            for feat in osm_data.get("features", []):
                osm_id = str(feat.get("properties", {}).get("@id") or feat.get("properties", {}).get("id") or "")
                if osm_id:
                    TINH_OSM_DICT[osm_id] = feat
            logger.info(f"Successfully cached {len(TINH_OSM_DICT)} OSM provinces.")
        except Exception as e:
            logger.error(f"Failed to load OSM provinces cache: {e}")
            
    diff_path = os.path.join(OUTPUT_DIR, "tinh_comparison", "difference.geojson")
    if os.path.exists(diff_path):
        try:
            with open(diff_path, "r", encoding="utf-8") as f:
                diff_data = json.load(f)
            for feat in diff_data.get("features", []):
                off_id = str(feat.get("properties", {}).get("official_id") or "")
                if off_id:
                    if off_id not in TINH_DIFF_DICT:
                        TINH_DIFF_DICT[off_id] = []
                    TINH_DIFF_DICT[off_id].append(feat)
            logger.info(f"Successfully cached difference shapes for {len(TINH_DIFF_DICT)} provinces.")
        except Exception as e:
            logger.error(f"Failed to load province difference cache: {e}")

# Pre-load Communes Caches
reload_tinh_cache()

OFFICIAL_DICT = {}
try:
    off_data = load_geojson("simplified", "official_communes.geojson")
    for feat in off_data.get("features", []):
        off_id = str(feat.get("properties", {}).get("a02_xa") or feat.get("properties", {}).get("id") or "")
        if off_id:
            OFFICIAL_DICT[off_id] = feat
    logger.info(f"Loaded {len(OFFICIAL_DICT)} official commune geometries.")
except Exception as e:
    logger.error(f"Failed to pre-load official communes: {e}")

OSM_DICT = {}
try:
    osm_data = load_geojson("simplified", "osm_communes.geojson")
    for feat in osm_data.get("features", []):
        osm_id = str(feat.get("properties", {}).get("@id") or feat.get("properties", {}).get("id") or "")
        if osm_id:
            OSM_DICT[osm_id] = feat
    logger.info(f"Loaded {len(OSM_DICT)} OSM commune geometries.")
except Exception as e:
    logger.error(f"Failed to pre-load OSM communes: {e}")

DIFF_DICT = {}  # Maps official_id -> list of difference features
try:
    diff_data = load_geojson("comparison", "difference.geojson")
    for feat in diff_data.get("features", []):
        off_id = str(feat.get("properties", {}).get("official_id") or "")
        if off_id:
            if off_id not in DIFF_DICT:
                DIFF_DICT[off_id] = []
            DIFF_DICT[off_id].append(feat)
    logger.info(f"Loaded differences for {len(DIFF_DICT)} communes.")
except Exception as e:
    logger.error(f"Failed to pre-load difference geometries: {e}")


@app.get("/")
def read_root():
    return {"message": "Welcome to GIS Province Regulator API"}

@app.get("/candidates/metadata")
def get_candidates_metadata():
    """Get candidates metadata list (lightweight, no geometry, for fast loading)"""
    path = os.path.join(OUTPUT_DIR, "candidates", "candidate.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading candidates metadata: {e}")
            return []
    return []

@app.get("/candidate/{official_id}/geometry")
def get_candidate_geometry(official_id: str, osm_id: str = "N/A"):
    """
    Get specific geometries for a single candidate commune on-demand:
    - Official geometry
    - OSM geometry
    - Difference geometries
    """
    official_id = str(official_id)
    osm_id = str(osm_id)
    
    official_geom = OFFICIAL_DICT.get(official_id)
    osm_geom = OSM_DICT.get(osm_id) if osm_id != "N/A" else None
    diff_geoms = DIFF_DICT.get(official_id, [])
    
    return {
        "official": official_geom,
        "osm": osm_geom,
        "difference": {
            "type": "FeatureCollection",
            "features": diff_geoms
        }
    }

@app.get("/statistics")
def get_statistics():
    """Get overall comparison statistics"""
    path = os.path.join(OUTPUT_DIR, "statistics", "statistics.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading statistics: {e}")
            return {}
    return {}

@app.get("/official/communes")
def get_official_communes():
    """Get simplified official boundary GeoJSON"""
    return load_geojson("simplified", "official_communes.geojson")

@app.get("/osm/communes")
def get_osm_communes():
    """Get simplified OSM boundary GeoJSON"""
    return load_geojson("simplified", "osm_communes.geojson")

@app.get("/difference")
def get_difference():
    """Get geometry differences GeoJSON"""
    return load_geojson("comparison", "difference.geojson")

@app.get("/missing")
def get_missing():
    """Get missing boundaries GeoJSON"""
    return load_geojson("comparison", "missing.geojson")

@app.get("/new")
def get_new():
    """Get new/extra boundaries GeoJSON"""
    return load_geojson("comparison", "new.geojson")

@app.get("/compare-results")
def get_compare_results():
    """Get detailed geometry comparison results"""
    path = os.path.join(OUTPUT_DIR, "comparison", "compare_result.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading compare results: {e}")
            return []
    return []

@app.get("/search")
def search_communes(q: str):
    """Search for communes by name in preloaded datasets"""
    q_clean = clean_name(q)
    if not q_clean:
        return {"features": []}
        
    results = []
    # Search in preloaded official commune records
    for fid, feat in OFFICIAL_DICT.items():
        name = str(feat.get("properties", {}).get("a03_ten") or "")
        if q_clean in clean_name(name):
            results.append(feat)
            
    # Search in preloaded OSM records
    existing_names = {clean_name(f.get("properties", {}).get("a03_ten") or "") for f in results}
    for oid, feat in OSM_DICT.items():
        name = str(feat.get("properties", {}).get("name") or "")
        if name and q_clean in clean_name(name):
            if clean_name(name) not in existing_names:
                results.append(feat)
                
    return {"features": results}

def reload_osm_and_diff_cache():
    global OSM_DICT, DIFF_DICT
    # Reload OSM communes simplified
    try:
        new_osm_dict = {}
        osm_data = load_geojson("simplified", "osm_communes.geojson")
        for feat in osm_data.get("features", []):
            osm_id = str(feat.get("properties", {}).get("@id") or feat.get("properties", {}).get("id") or "")
            if osm_id:
                new_osm_dict[osm_id] = feat
        OSM_DICT = new_osm_dict
        logger.info("Successfully reloaded OSM simplified boundary cache.")
    except Exception as e:
        logger.error(f"Failed to reload OSM simplified boundary cache: {e}")

    # Reload Difference geometries
    try:
        new_diff_dict = {}
        diff_data = load_geojson("comparison", "difference.geojson")
        for feat in diff_data.get("features", []):
            off_id = str(feat.get("properties", {}).get("official_id") or "")
            if off_id:
                if off_id not in new_diff_dict:
                    new_diff_dict[off_id] = []
                new_diff_dict[off_id].append(feat)
        DIFF_DICT = new_diff_dict
        logger.info("Successfully reloaded Difference geometries cache.")
    except Exception as e:
        logger.error(f"Failed to reload Difference geometries cache: {e}")

class EditOSMRequest(BaseModel):
    official_id: str
    osm_id: str
    action: str

@app.post("/api/edit-osm")
def edit_osm(payload: EditOSMRequest):
    """
    Apply edit to GeoJSON files, candidate metadata, and generate JOSM XML.
    """
    logger.info(f"OSM edit API called for official_id: {payload.official_id}, osm_id: {payload.osm_id}, action: {payload.action}")
    
    # Execute editing logic via imported scripts module
    result = apply_edit(payload.action, payload.official_id, payload.osm_id)
    
    if result.get("status") == "success":
        # Hot-reload in-memory caches to immediately reflect on WebGIS
        reload_osm_and_diff_cache()
        
    return result

# --- PROVINCE & NATIONAL BOUNDARY REGULATOR ENDPOINTS ---

@app.get("/tinh/candidates/metadata")
def get_tinh_candidates_metadata():
    """Get province candidates metadata list"""
    path = os.path.join(OUTPUT_DIR, "tinh_candidates", "candidate.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading province candidates: {e}")
            return []
    return []

@app.get("/tinh/candidate/{official_id}/geometry")
def get_tinh_candidate_geometry(official_id: str, osm_id: str = "N/A"):
    """Get geometry comparison data for a province/national boundary on demand"""
    official_id = str(official_id)
    osm_id = str(osm_id)
    
    official_geom = TINH_OFFICIAL_DICT.get(official_id)
    osm_geom = TINH_OSM_DICT.get(osm_id) if osm_id != "N/A" else None
    diff_geoms = TINH_DIFF_DICT.get(official_id, [])
    
    return {
        "official": official_geom,
        "osm": osm_geom,
        "difference": {
            "type": "FeatureCollection",
            "features": diff_geoms
        }
    }

@app.get("/tinh/statistics")
def get_tinh_statistics():
    """Get overall statistics for province-level comparison"""
    path = os.path.join(OUTPUT_DIR, "tinh_statistics", "statistics.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading province statistics: {e}")
            return {}
    return {}

@app.get("/tinh/official/provinces")
def get_tinh_official_provinces():
    """Get official province boundary GeoJSON (simplified)"""
    return load_geojson("simplified", "tinh_official_communes.geojson")

@app.get("/tinh/osm/provinces")
def get_tinh_osm_provinces():
    """Get OSM province boundary GeoJSON (simplified)"""
    return load_geojson("simplified", "tinh_osm_communes.geojson")

@app.get("/tinh/difference")
def get_tinh_difference():
    """Get province difference geometries"""
    return load_geojson("tinh_comparison", "difference.geojson")

@app.get("/tinh/missing")
def get_tinh_missing():
    """Get missing province boundaries"""
    return load_geojson("tinh_comparison", "missing.geojson")

@app.get("/tinh/new")
def get_tinh_new():
    """Get new/unmatched OSM province boundaries"""
    return load_geojson("tinh_comparison", "new.geojson")

@app.get("/tinh/compare-results")
def get_tinh_compare_results():
    """Get comparison details for all matched provinces"""
    path = os.path.join(OUTPUT_DIR, "tinh_comparison", "compare_result.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading province comparison list: {e}")
            return []
    return []

@app.get("/tinh/search")
def search_provinces(q: str):
    """Search for provinces by name in cached datasets"""
    q_clean = clean_name(q)
    if not q_clean:
        return {"features": []}
        
    results = []
    for fid, feat in TINH_OFFICIAL_DICT.items():
        name = str(feat.get("properties", {}).get("a01_ten") or "")
        if q_clean in clean_name(name):
            results.append(feat)
            
    existing_names = {clean_name(f.get("properties", {}).get("a01_ten") or "") for f in results}
    for oid, feat in TINH_OSM_DICT.items():
        name = str(feat.get("properties", {}).get("name") or "")
        if name and q_clean in clean_name(name):
            if clean_name(name) not in existing_names:
                results.append(feat)
                
    return {"features": results}

class EditTinhRequest(BaseModel):
    official_id: str
    osm_id: str
    action: str

@app.post("/tinh/api/edit-tinh")
def edit_tinh(payload: EditTinhRequest):
    """Apply edit/sync for province and reload the cache"""
    logger.info(f"Province edit API called for official_id: {payload.official_id}, osm_id: {payload.osm_id}, action: {payload.action}")
    result = apply_tinh_edit(payload.action, payload.official_id, payload.osm_id)
    if result.get("status") == "success":
        reload_tinh_cache()
    return result

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting WebGIS API Server on port 8000...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
