import os
import sys
import json
import logging
import pandas as pd
import geopandas as gpd

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("candidate")

class CandidateGenerator:
    """
    Classifies boundary comparison results into actionable categories:
    - Matched: Perfect matches (overlap >= 98% and name match >= 90%)
    - Need Update: Geometry discrepancy (overlap < 98% but name matches)
    - Need Review: Mismatches or ambiguous cases (e.g. high overlap but name mismatch)
    - Missing: Official boundaries that do not exist in OSM.
    Outputs: candidate.json, candidate.csv, candidate.geojson.
    """
    def __init__(self, compare_results: list, missing_features: list, off_gdf: gpd.GeoDataFrame):
        self.compare_results = compare_results
        self.missing_features = missing_features
        self.off_gdf = off_gdf

    def generate(self, output_dir: str):
        logger.info("Generating Candidates for AI and review...")
        os.makedirs(output_dir, exist_ok=True)

        candidates = []
        
        # Build a lookup for 4326 geometries from the official dataset
        off_id_col = 'a02_xa' if 'a02_xa' in self.off_gdf.columns else (
            'id' if 'id' in self.off_gdf.columns else self.off_gdf.index.name or 'index'
        )
        
        # Reproject to 4326 for final GeoJSON storage
        off_4326 = self.off_gdf.to_crs(epsg=4326)
        geom_lookup = {}
        for _, row in off_4326.iterrows():
            geom_lookup[str(row[off_id_col])] = row['geometry']

        # 1. Process comparison results
        for r in self.compare_results:
            off_id = str(r['official_id'])
            off_name = r['official_name']
            province = r['province']
            osm_id = r['osm_id']
            osm_name = r['osm_name']
            overlap = r['overlap_ratio']
            name_sim = r['name_similarity']
            
            # Category decision tree
            if overlap >= 0.98 and name_sim >= 0.90:
                category = "Matched"
                reason = "Perfect match in geometry and name."
            elif overlap >= 0.95 and name_sim < 0.80:
                category = "Need Review"
                reason = "High spatial overlap, but name differs (Possible renaming needed)."
            elif overlap < 0.98 and overlap >= 0.50 and name_sim >= 0.80:
                category = "Need Update"
                reason = "Names match, but geometry has significant differences."
            else:
                category = "Need Review"
                reason = "Significant difference in geometry and/or name. Needs manual check."

            # Fetch geometry
            geom = geom_lookup.get(off_id)
            
            candidates.append({
                "official_id": off_id,
                "official_name": off_name,
                "province": province,
                "osm_id": osm_id,
                "osm_name": osm_name,
                "category": category,
                "overlap_ratio": overlap,
                "name_similarity": name_sim,
                "reason": reason,
                "geometry": geom
            })

        # 2. Add Missing features from Official
        for f in self.missing_features:
            props = f["properties"]
            off_id = str(props["official_id"])
            off_name = props["official_name"]
            province = props["province"]
            
            geom = geom_lookup.get(off_id)
            
            candidates.append({
                "official_id": off_id,
                "official_name": off_name,
                "province": province,
                "osm_id": "N/A",
                "osm_name": "N/A",
                "category": "Missing",
                "overlap_ratio": 0.0,
                "name_similarity": 0.0,
                "reason": "Official commune boundary not found in OSM.",
                "geometry": geom
            })

        # 3. Export to CSV, JSON, and GeoJSON
        # We must create a clean DataFrame for CSV/JSON exports (excluding geometry)
        df_out = pd.DataFrame([{k: v for k, v in c.items() if k != 'geometry'} for c in candidates])
        
        json_path = os.path.join(output_dir, "candidate.json")
        df_out.to_json(json_path, orient="records", force_ascii=False, indent=4)
        
        csv_path = os.path.join(output_dir, "candidate.csv")
        df_out.to_csv(csv_path, index=False, encoding="utf-8")

        # GeoJSON export using GeoPandas
        geojson_features = []
        for c in candidates:
            if c['geometry'] is not None and not c['geometry'].is_empty:
                geojson_features.append({
                    "type": "Feature",
                    "geometry": c['geometry'].__geo_interface__,
                    "properties": {k: v for k, v in c.items() if k != 'geometry'}
                })
                
        geojson_path = os.path.join(output_dir, "candidate.geojson")
        with open(geojson_path, "w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "features": geojson_features}, f, ensure_ascii=False)

        logger.info(f"Candidate generator complete. Saved {len(candidates)} candidates to {output_dir}")
        return candidates

if __name__ == "__main__":
    import time
    from loader import GeoJSONLoader
    
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    compare_res_path = os.path.join(root_dir, "output", "comparison", "compare_result.json")
    missing_path = os.path.join(root_dir, "output", "comparison", "missing.geojson")
    off_path = os.path.join(root_dir, "data", "official", "boundary.geojson")
    
    print("=" * 60)
    print("BENCHMARK: AI CANDIDATE GENERATION")
    print("=" * 60)
    
    if os.path.exists(compare_res_path) and os.path.exists(missing_path) and os.path.exists(off_path):
        # Load comparison results
        print(f"Loading comparison results from: {compare_res_path}")
        with open(compare_res_path, "r", encoding="utf-8") as f:
            compare_results = json.load(f)
            
        # Load missing features
        print(f"Loading missing features from: {missing_path}")
        with open(missing_path, "r", encoding="utf-8") as f:
            missing_features = json.load(f).get("features", [])
            
        # Load official data for geometry lookup
        print("Loading official dataset...")
        off_gdf = GeoJSONLoader(off_path, "Official").load()
            
        # Run Candidate Generator
        print("Generating AI candidates...")
        start = time.time()
        candidate_gen = CandidateGenerator(compare_results, missing_features, off_gdf)
        out_dir = os.path.join(root_dir, "output", "candidates")
        candidates = candidate_gen.generate(out_dir)
        end = time.time()
        
        print(f"--> Candidates phase completed in: {end - start:.2f} seconds")
    else:
        print("Required comparison outputs or official dataset not found.")
        print("Please run compare.py first.")
        
    print("=" * 60)
