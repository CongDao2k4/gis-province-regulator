import os
import sys
import json
import time
import argparse
import unicodedata
import re
from shapely.geometry import shape, mapping

def clean_name(name: str) -> str:
    """Normalize and clean administrative names for spelling standardization."""
    if not name:
        return ""
    n = unicodedata.normalize('NFC', name.lower())
    tone_replacements = {
        "oà": "òa", "oá": "óa", "oả": "ỏa", "oã": "õa", "oạ": "ọa",
        "oè": "òe", "oé": "óe", "oẻ": "ỏe", "oẽ": "õe", "oẹ": "ọe",
        "uỳ": "ùy", "uý": "úy", "uỷ": "ủy", "uỹ": "ũy", "uỵ": "ụy",
        "uỳ": "ùy", "uý": "uý", "uỷ": "uỷ", "uỹ": "uỹ", "uỵ": "uự"
    }
    for k, v in tone_replacements.items():
        n = n.replace(k, v)
    prefixes = [
        r"^xã\s+", r"^phường\s+", r"^thị\s*trấn\s+", r"^thị\s*xã\s+",
        r"^huyện\s+", r"^quận\s+", r"^thành\s*phố\s+", r"^tỉnh\s+",
        r"^thủ\s*đô\s+"
    ]
    for pattern in prefixes:
        n = re.sub(pattern, "", n)
    n = re.sub(r'[^\w\s]', ' ', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n

def create_josm_relation_xml(geom, relation_id, name, action_tag='action="modify"'):
    """Generate JOSM XML elements (nodes, ways, relation) for a given shapely geometry."""
    nodes = []
    ways = []
    members = []
    
    node_id_counter = -1000
    way_id_counter = -100
    
    # Extract polygons
    polygons = []
    if geom.geom_type == 'Polygon':
        polygons = [geom]
    elif geom.geom_type == 'MultiPolygon':
        polygons = list(geom.geoms)
        
    def add_way(coords, role):
        nonlocal node_id_counter, way_id_counter
        way_nodes = []
        for lon, lat in coords:
            nodes.append(f'  <node id="{node_id_counter}" lat="{lat:.7f}" lon="{lon:.7f}" {action_tag} />')
            way_nodes.append(node_id_counter)
            node_id_counter -= 1
            
        ways.append(f'  <way id="{way_id_counter}" {action_tag}>')
        for nid in way_nodes:
            ways.append(f'    <nd ref="{nid}" />')
        ways.append('  </way>')
        
        ref_id = way_id_counter
        way_id_counter -= 1
        return ref_id, role

    for poly in polygons:
        # Simplify geometry slightly for OSM upload (~5m)
        poly_simp = poly.simplify(0.00005, preserve_topology=True)
        if poly_simp.geom_type != 'Polygon':
            poly_simp = poly
            
        ext_id, role = add_way(list(poly_simp.exterior.coords), "outer")
        members.append((ext_id, role))
        
        for interior in poly_simp.interiors:
            int_id, role = add_way(list(interior.coords), "inner")
            members.append((int_id, role))
            
    admin_level = "8" if ("phường" in name.lower() or "thị trấn" in name.lower()) else "9"
    
    relation_xml = []
    relation_xml.append(f'  <relation id="{relation_id}" {action_tag}>')
    for way_id, role in members:
        relation_xml.append(f'    <member type="way" ref="{way_id}" role="{role}" />')
        
    relation_xml.append('    <tag k="type" v="boundary" />')
    relation_xml.append('    <tag k="boundary" v="administrative" />')
    relation_xml.append(f'    <tag k="admin_level" v="{admin_level}" />')
    relation_xml.append(f'    <tag k="name" v="{name}" />')
    relation_xml.append('    <tag k="source" v="Dữ liệu Bản đồ Hành chính Việt Nam 2025 (API Sync)" />')
    relation_xml.append('  </relation>')
    
    return nodes, ways, relation_xml

def apply_edit(action: str, official_id: str, osm_id: str) -> dict:
    """
    Main function to apply spatial edit to boundary.geojson datasets.
    """
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Paths
    osm_path = os.path.join(root_dir, "data", "osm", "boundary.geojson")
    off_path = os.path.join(root_dir, "data", "official", "boundary.geojson")
    osm_sim_path = os.path.join(root_dir, "output", "simplified", "osm_communes.geojson")
    candidates_path = os.path.join(root_dir, "output", "candidates", "candidate.json")
    josm_changes_path = os.path.join(root_dir, "output", "osm_changes.osm")
    
    # Load raw datasets
    if not os.path.exists(osm_path) or not os.path.exists(off_path):
        return {"status": "error", "message": "Dữ liệu GeoJSON gốc của OSM hoặc Official không tồn tại."}
        
    with open(osm_path, "r", encoding="utf-8") as f:
        osm_geojson = json.load(f)
    with open(off_path, "r", encoding="utf-8") as f:
        off_geojson = json.load(f)
        
    # Find official feature
    off_feat = None
    for feat in off_geojson.get("features", []):
        props = feat.get("properties", {})
        fid = str(props.get("a02_xa") or feat.get("id") or "")
        if fid == official_id:
            off_feat = feat
            break
            
    if off_feat is None and action in ["update", "modify", "create"]:
        return {"status": "error", "message": f"Không tìm thấy xã Official có ID: {official_id}"}
        
    new_osm_id = osm_id
    updated_geom = None
    commune_name = off_feat.get("properties", {}).get("a03_ten", "Không tên") if off_feat else "Xóa xã"
    
    # 1. Update data/osm/boundary.geojson
    features = osm_geojson.get("features", [])
    
    if action in ["update", "modify"]:
        found = False
        for feat in features:
            fid = str(feat.get("properties", {}).get("@id") or feat.get("id") or "")
            if fid == osm_id:
                # Cập nhật geometry và thuộc tính từ Official
                feat["geometry"] = off_feat["geometry"]
                updated_geom = shape(off_feat["geometry"])
                # Đồng bộ tên gọi
                feat["properties"]["name"] = off_feat["properties"]["a03_ten"]
                found = True
                break
        if not found:
            return {"status": "error", "message": f"Không tìm thấy xã OSM có ID: {osm_id} để cập nhật."}
            
    elif action == "create":
        # Tạo ID âm độc nhất dựa trên timestamp
        new_osm_id = f"-{int(time.time() * 10) % 10000000}"
        new_feat = {
            "type": "Feature",
            "id": new_osm_id,
            "geometry": off_feat["geometry"],
            "properties": {
                "@id": new_osm_id,
                "name": off_feat["properties"]["a03_ten"],
                "boundary": "administrative",
                "admin_level": "8" if ("phường" in commune_name.lower() or "thị trấn" in commune_name.lower()) else "9"
            }
        }
        features.append(new_feat)
        updated_geom = shape(off_feat["geometry"])
        
    elif action == "delete":
        # Tìm và xóa khỏi danh sách
        original_len = len(features)
        features = [f for f in features if str(f.get("properties", {}).get("@id") or f.get("id") or "") != osm_id]
        if len(features) == original_len:
            return {"status": "error", "message": f"Không tìm thấy xã OSM có ID: {osm_id} để xóa."}
        osm_geojson["features"] = features
        
    # Save raw OSM geojson
    with open(osm_path, "w", encoding="utf-8") as f:
        json.dump(osm_geojson, f, ensure_ascii=False)
        
    # 2. Update output/simplified/osm_communes.geojson (for WebGIS fast updates)
    if os.path.exists(osm_sim_path):
        with open(osm_sim_path, "r", encoding="utf-8") as f:
            sim_geojson = json.load(f)
            
        sim_features = sim_geojson.get("features", [])
        if action in ["update", "modify"]:
            for feat in sim_features:
                fid = str(feat.get("properties", {}).get("@id") or feat.get("id") or "")
                if fid == osm_id:
                    # Simplify to 0.001 degree
                    simplified_shape = updated_geom.simplify(0.001, preserve_topology=True)
                    feat["geometry"] = mapping(simplified_shape)
                    feat["properties"]["name"] = commune_name
                    break
        elif action == "create":
            simplified_shape = updated_geom.simplify(0.001, preserve_topology=True)
            new_sim_feat = {
                "type": "Feature",
                "id": new_osm_id,
                "geometry": mapping(simplified_shape),
                "properties": {
                    "@id": new_osm_id,
                    "name": commune_name
                }
            }
            sim_features.append(new_sim_feat)
        elif action == "delete":
            sim_features = [f for f in sim_features if str(f.get("properties", {}).get("@id") or f.get("id") or "") != osm_id]
            sim_geojson["features"] = sim_features
            
        with open(osm_sim_path, "w", encoding="utf-8") as f:
            json.dump(sim_geojson, f, ensure_ascii=False)
            
    # 3. Update candidate.json (Move to Matched tab)
    if os.path.exists(candidates_path):
        with open(candidates_path, "r", encoding="utf-8") as f:
            candidates = json.load(f)
            
        if action in ["update", "modify", "create"]:
            found_candidate = False
            for cand in candidates:
                if str(cand.get("official_id")) == official_id:
                    cand["category"] = "Matched"
                    cand["osm_id"] = new_osm_id
                    cand["osm_name"] = commune_name
                    cand["overlap_ratio"] = 1.0
                    cand["iou"] = 1.0
                    cand["reason"] = "Đã được đồng bộ hóa thành công qua API đối soát."
                    found_candidate = True
                    break
            if not found_candidate and action == "create":
                # Thêm mới candidate ở dạng Matched
                candidates.append({
                    "official_id": official_id,
                    "official_name": commune_name,
                    "province": off_feat["properties"].get("a04_tentinh", "N/A"),
                    "osm_id": new_osm_id,
                    "osm_name": commune_name,
                    "overlap_ratio": 1.0,
                    "iou": 1.0,
                    "category": "Matched",
                    "reason": "Đã được thêm mới và đồng bộ thành công."
                })
        elif action == "delete":
            # Khi xóa ranh giới thừa, ta chuyển trạng thái candidate thừa đó sang dạng đã xử lý (hoặc xóa khỏi candidates)
            candidates = [c for c in candidates if str(c.get("osm_id")) != osm_id]
            
        with open(candidates_path, "w", encoding="utf-8") as f:
            json.dump(candidates, f, ensure_ascii=False, indent=4)
            
    # 5. Clean up difference geometries and lists under output/comparison/
    comp_dir = os.path.join(root_dir, "output", "comparison")
    
    # Clean output/comparison/difference.geojson
    diff_path = os.path.join(comp_dir, "difference.geojson")
    if os.path.exists(diff_path):
        try:
            with open(diff_path, "r", encoding="utf-8") as f:
                diff_geojson = json.load(f)
            diff_geojson["features"] = [
                feat for feat in diff_geojson.get("features", [])
                if str(feat.get("properties", {}).get("official_id")) != official_id
            ]
            with open(diff_path, "w", encoding="utf-8") as f:
                json.dump(diff_geojson, f, ensure_ascii=False)
        except Exception as e:
            print(f"[!] Warning: Failed to update difference.geojson: {e}")

    # Clean output/comparison/missing.geojson
    missing_path = os.path.join(comp_dir, "missing.geojson")
    if os.path.exists(missing_path):
        try:
            with open(missing_path, "r", encoding="utf-8") as f:
                missing_geojson = json.load(f)
            missing_geojson["features"] = [
                feat for feat in missing_geojson.get("features", [])
                if str(feat.get("properties", {}).get("a02_xa")) != official_id
            ]
            with open(missing_path, "w", encoding="utf-8") as f:
                json.dump(missing_geojson, f, ensure_ascii=False)
        except Exception as e:
            print(f"[!] Warning: Failed to update missing.geojson: {e}")

    # Clean output/comparison/new.geojson
    new_path = os.path.join(comp_dir, "new.geojson")
    if os.path.exists(new_path):
        try:
            with open(new_path, "r", encoding="utf-8") as f:
                new_geojson = json.load(f)
            new_geojson["features"] = [
                feat for feat in new_geojson.get("features", [])
                if str(feat.get("properties", {}).get("osm_id") or feat.get("id")) != osm_id
            ]
            with open(new_path, "w", encoding="utf-8") as f:
                json.dump(new_geojson, f, ensure_ascii=False)
        except Exception as e:
            print(f"[!] Warning: Failed to update new.geojson: {e}")
            
    # 4. Generate/Append JOSM Change XML (osm_changes.osm)
    if action in ["update", "modify", "create"] and updated_geom:
        nodes, ways, relation = create_josm_relation_xml(updated_geom, new_osm_id, commune_name)
        
        # We append to output/osm_changes.osm if exists, or write new one
        existing_xml = ""
        if os.path.exists(josm_changes_path):
            try:
                with open(josm_changes_path, "r", encoding="utf-8") as f:
                    existing_xml = f.read()
            except Exception:
                pass
                
        # Parse existing XML elements or construct a new file
        if existing_xml and "<osm" in existing_xml:
            # Strip </osm> and insert new elements
            base_xml = existing_xml.split("</osm>")[0]
            new_elements = "\n".join(nodes) + "\n" + "\n".join(ways) + "\n" + "\n".join(relation) + "\n"
            final_xml = base_xml + new_elements + "</osm>\n"
        else:
            final_xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
            final_xml += '<osm version="0.6" generator="ProvinceRegulator" upload="true">\n'
            final_xml += "\n".join(nodes) + "\n"
            final_xml += "\n".join(ways) + "\n"
            final_xml += "\n".join(relation) + "\n"
            final_xml += '</osm>\n'
            
        with open(josm_changes_path, "w", encoding="utf-8") as f:
            f.write(final_xml)
            
    return {
        "status": "success",
        "message": f"Đồng bộ thành công ranh giới cho xã {commune_name}.",
        "osm_id": new_osm_id
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Script cập nhật ranh giới OSM thủ công/hoặc qua CLI.")
    parser.add_argument("--action", required=True, choices=["update", "modify", "create", "delete"], help="Hành động sửa ranh giới")
    parser.add_argument("--official_id", required=False, default="", help="ID xã Official (cần thiết cho update/modify/create)")
    parser.add_argument("--osm_id", required=False, default="", help="ID xã OSM (cần thiết cho update/modify/delete)")
    
    args = parser.parse_args()
    
    if args.action in ["update", "modify", "create"] and not args.official_id:
        print("[!] Lỗi: Cần truyền --official_id cho hành động update, modify hoặc create.")
        sys.exit(1)
    if args.action in ["update", "modify", "delete"] and not args.osm_id:
        print("[!] Lỗi: Cần truyền --osm_id cho hành động update, modify hoặc delete.")
        sys.exit(1)
        
    result = apply_edit(args.action, args.official_id, args.osm_id)
    print(f"[{result['status'].upper()}] {result['message']}")
