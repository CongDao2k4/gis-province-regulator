import os
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

class EditOSMRequest(BaseModel):
    official_id: str
    osm_id: str
    action: str

@app.post("/api/edit-osm")
def edit_osm(payload: EditOSMRequest):
    """
    Mock API endpoint to edit OpenStreetMap.
    This simulates saving, adding, or deleting relation geometries in OSM database.
    """
    logger.info(f"OSM edit API called for official_id: {payload.official_id}, osm_id: {payload.osm_id}, action: {payload.action}")
    
    action_text = "chuẩn hóa ranh giới"
    if payload.action == "create":
        action_text = "thêm mới xã"
    elif payload.action == "delete":
        action_text = "xóa ranh giới thừa"
        
    return {
        "status": "success",
        "message": f"Đồng bộ thành công! Yêu cầu {action_text} đối với ID {payload.osm_id or payload.official_id} đã được gửi lên OpenStreetMap."
    }

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting WebGIS API Server on port 8000...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
