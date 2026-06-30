import os
import sys
import json
import logging
import geopandas as gpd

# Add project root to path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("tinh_candidate")

class ProvinceCandidateGenerator:
    """
    Groups matched and unmatched Province/National boundaries, categorizing them into actions.
    """
    def __init__(self, matches: list, unmatched_official: list, unmatched_osm: list, off_gdf: gpd.GeoDataFrame):
        self.matches = matches
        self.unmatched_official = unmatched_official
        self.unmatched_osm = unmatched_osm
        self.off_gdf = off_gdf
        
    def generate(self, output_dir: str):
        logger.info("Generating province candidate files...")
        os.makedirs(output_dir, exist_ok=True)
        
        candidates = []
        off_id_col = 'a02_tinh' if 'a02_tinh' in self.off_gdf.columns else 'id'
        off_dict = {str(row[off_id_col]): row for _, row in self.off_gdf.iterrows()}
        
        # Process matches
        for m in self.matches:
            off_id = m['official_id']
            off_name = m['official_name']
            osm_id = m['osm_id']
            osm_name = m['osm_name']
            overlap = m['overlap_ratio']
            name_sim = m['name_similarity']
            
            # Decision logic at 95% threshold
            if overlap >= 0.95 and name_sim >= 0.80:
                category = "Matched"
                reason = "Trùng khớp hoàn hảo cả hình học và tên gọi."
            elif overlap >= 0.95 and name_sim < 0.80:
                category = "Need Review"
                reason = "Độ chồng đè cao nhưng tên khác biệt (Cần kiểm tra đổi tên)."
            elif overlap < 0.95 and overlap >= 0.50 and name_sim >= 0.80:
                category = "Need Update"
                reason = "Tên khớp nhưng ranh giới hình học bị lệch (Cần sửa lại ranh giới)."
            else:
                category = "Need Review"
                reason = "Ranh giới hoặc tên gọi có sai lệch lớn. Cần kiểm tra thủ công."
                
            candidates.append({
                "official_id": off_id,
                "official_name": off_name,
                "province": off_name,
                "osm_id": osm_id,
                "osm_name": osm_name,
                "overlap_ratio": overlap,
                "name_similarity": name_sim,
                "category": category,
                "reason": reason
            })
            
        # Process unmatched official (Missing)
        for u in self.unmatched_official:
            candidates.append({
                "official_id": u['official_id'],
                "official_name": u['official_name'],
                "province": u['official_name'],
                "osm_id": "N/A",
                "osm_name": "N/A",
                "overlap_ratio": 0.0,
                "name_similarity": 0.0,
                "category": "Missing",
                "reason": "Tỉnh có trong dữ liệu gốc của Nhà nước nhưng hoàn toàn thiếu trên OSM."
            })
            
        # Process unmatched OSM (New / Excess OSM relations)
        for u in self.unmatched_osm:
            candidates.append({
                "official_id": "N/A",
                "official_name": "N/A",
                "province": "N/A",
                "osm_id": u['osm_id'],
                "osm_name": u['name'],
                "overlap_ratio": 0.0,
                "name_similarity": 0.0,
                "category": "New",
                "reason": "Ranh giới thừa trên OSM không tương ứng với tỉnh nào của Nhà nước."
            })
            
        # Save candidates metadata JSON
        cand_path = os.path.join(output_dir, "candidate.json")
        with open(cand_path, "w", encoding="utf-8") as f:
            json.dump(candidates, f, ensure_ascii=False, indent=4)
            
        logger.info(f"Saved {len(candidates)} candidates to {cand_path}")
        return candidates
