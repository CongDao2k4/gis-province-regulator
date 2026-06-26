import os
import json
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

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

@app.get("/")
def read_root():
    return {"message": "Welcome to GIS Province Regulator API"}

@app.get("/official/communes")
def get_official_communes():
    """Get list of Official boundary communes (simplified for performance)"""
    return load_geojson("simplified", "official_communes.geojson")

@app.get("/osm/communes")
def get_osm_communes():
    """Get list of OSM boundary communes (simplified for performance)"""
    return load_geojson("simplified", "osm_communes.geojson")

@app.get("/difference")
def get_difference():
    """Get spatial differences (red/blue/yellow/purple layer)"""
    return load_geojson("comparison", "difference.geojson")

@app.get("/missing")
def get_missing_communes():
    """Get boundaries that are missing in OSM"""
    return load_geojson("comparison", "missing.geojson")

@app.get("/new")
def get_new_communes():
    """Get boundaries that are new/unmatched in OSM"""
    return load_geojson("comparison", "new.geojson")

@app.get("/candidates")
def get_candidates():
    """Get candidates for AI review"""
    return load_geojson("candidates", "candidate.geojson")

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

@app.get("/search")
def search_features(q: str):
    """Search official communes by name"""
    data = load_geojson("simplified", "official_communes.geojson")
    results = []
    q = q.lower().strip()
    if not q:
        return {"type": "FeatureCollection", "features": []}
        
    for feat in data.get("features", []):
        props = feat.get("properties", {})
        # Check standard name columns
        name_val = props.get("a03_ten") or props.get("name") or ""
        if q in str(name_val).lower():
            results.append(feat)
            
    return {"type": "FeatureCollection", "features": results}

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting WebGIS API Server on port 8000...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
