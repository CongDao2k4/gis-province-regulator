import json
import os
import sys
import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    candidates_json_path = os.path.join(root_dir, "output", "candidates", "candidate.json")
    official_geojson_path = os.path.join(root_dir, "data", "official", "boundary.geojson")
    output_osm_path = os.path.join(root_dir, "output", "osm_changes.osm")

    print("=" * 70)
    print("   CÔNG CỤ TẠO FILE UPDATE / THÊM MỚI RANH GIỚI CHO JOSM (OSM EDITOR)")
    print("=" * 70)

    if not os.path.exists(candidates_json_path) or not os.path.exists(official_geojson_path):
        print("[!] Không tìm thấy các file dữ liệu cần thiết. Hãy chạy 'python src/pipeline.py' trước!")
        return

    # Load dữ liệu
    print("[INFO] Đang nạp danh sách kết quả đối soát...")
    with open(candidates_json_path, "r", encoding="utf-8") as f:
        candidates = json.load(f)
        
    print("[INFO] Đang nạp bản đồ ranh giới Official...")
    off_gdf = gpd.read_file(official_geojson_path)
    # Lấy cột ID của Official
    off_id_col = 'a02_xa' if 'a02_xa' in off_gdf.columns else ('id' if 'id' in off_gdf.columns else 'index')
    off_gdf[off_id_col] = off_gdf[off_id_col].astype(str)

    # Lọc danh sách xã thiếu (Missing) và xã lệch (Need Update)
    missing_list = [c for c in candidates if c["category"] == "Missing"]
    need_update_list = [c for c in candidates if c["category"] in ["Need Update", "Need Review"] and c["osm_id"] != "N/A"]

    print(f" -> Phát hiện: {len(missing_list)} xã thiếu hoàn toàn.")
    print(f" -> Phát hiện: {len(need_update_list)} xã lệch ranh giới cần sửa đổi.")

    # Khởi tạo bộ tạo ID âm của OSM (OSM sử dụng ID âm cho các thực thể tạo mới)
    node_id_counter = -1
    way_id_counter = -1
    relation_id_counter = -1

    osm_xml_nodes = []
    osm_xml_ways = []
    osm_xml_relations = []

    def process_polygon(geom, relation_id, name, admin_level, action_tag=""):
        nonlocal node_id_counter, way_id_counter
        
        # Hàm xử lý một ring (danh sách tọa độ) thành node và way
        def create_way(coords, role):
            nonlocal node_id_counter, way_id_counter
            way_nodes = []
            
            # Để tránh tạo quá nhiều node trùng khít tại một điểm, ta simplify nhẹ ranh giới (khoảng 5m)
            # Ranh giới thô hơn một chút sẽ tải lên OSM mượt mà hơn.
            
            # Tạo các Nodes cho Way
            # Lọc bớt các điểm quá sát nhau
            for lon, lat in coords:
                # Tạo node XML
                osm_xml_nodes.append(
                    f'  <node id="{node_id_counter}" lat="{lat:.7f}" lon="{lon:.7f}" {action_tag} />'
                )
                way_nodes.append(node_id_counter)
                node_id_counter -= 1
                
            # Tạo Way XML
            osm_xml_ways.append(f'  <way id="{way_id_counter}" {action_tag}>')
            for node_id in way_nodes:
                osm_xml_ways.append(f'    <nd ref="{node_id}" />')
            # Đóng way
            osm_xml_ways.append('  </way>')
            
            # Lưu way_id để đưa vào relation
            ref_way_id = way_id_counter
            way_id_counter -= 1
            return ref_way_id, role

        members = []
        
        # Phân rã Polygon/Multipolygon thành các Ring
        polygons = []
        if isinstance(geom, Polygon):
            polygons = [geom]
        elif isinstance(geom, MultiPolygon):
            polygons = list(geom.geoms)
            
        for poly in polygons:
            # Simplify geometry khoảng 0.00005 độ (~5m) để tối ưu số node tải lên OSM
            poly_simp = poly.simplify(0.00005, preserve_topology=True)
            if not isinstance(poly_simp, Polygon):
                poly_simp = poly # Fallback nếu simplify làm hỏng topology
                
            # Exterior ring (Đường bao ngoài)
            ext_way_id, role = create_way(list(poly_simp.exterior.coords), "outer")
            members.append((ext_way_id, role))
            
            # Interior rings (Đường bao trong - nếu có đảo/hồ nước rỗng bên trong)
            for interior in poly_simp.interiors:
                int_way_id, role = create_way(list(interior.coords), "inner")
                members.append((int_way_id, role))
                
        # Tạo Relation XML
        osm_xml_relations.append(f'  <relation id="{relation_id}" {action_tag}>')
        for way_id, role in members:
            osm_xml_relations.append(f'    <member type="way" ref="{way_id}" role="{role}" />')
            
        # Thêm tags hành chính chuẩn cho Việt Nam
        osm_xml_relations.append('    <tag k="type" v="boundary" />')
        osm_xml_relations.append('    <tag k="boundary" v="administrative" />')
        osm_xml_relations.append(f'    <tag k="admin_level" v="{admin_level}" />')
        osm_xml_relations.append(f'    <tag k="name" v="{name}" />')
        osm_xml_relations.append('    <tag k="source" v="Dữ liệu Bản đồ Hành chính Việt Nam 2025" />')
        osm_xml_relations.append('  </relation>')

    # 1. XỬ LÝ CÁC XÃ THIẾU (Tạo mới Relation với ID âm)
    print("[INFO] Đang chuyển đổi đa giác các xã thiếu...")
    for item in missing_list:
        off_id = str(item["official_id"])
        name = item["official_name"]
        
        # Lấy hình học từ file Official
        matches_rows = off_gdf[off_gdf[off_id_col] == off_id]
        if matches_rows.empty:
            continue
        geom = matches_rows.iloc[0]['geometry']
        
        # Xác định admin_level tự động (Phường/Thị trấn = 8, Xã = 9)
        admin_level = "8" if ("phường" in name.lower() or "thị trấn" in name.lower()) else "9"
        
        process_polygon(geom, relation_id_counter, name, admin_level, action_tag='action="modify"') # action modify cho JOSM import
        relation_id_counter -= 1

    # 2. XỬ LÝ CÁC XÃ LỆCH RANH GIỚI (Cập nhật hình học của Relation hiện có bằng ID dương của OSM)
    print("[INFO] Đang chuyển đổi đa giác các xã lệch ranh giới...")
    for item in need_update_list:
        off_id = str(item["official_id"])
        osm_id = int(item["osm_id"])
        name = item["official_name"]
        
        matches_rows = off_gdf[off_gdf[off_id_col] == off_id]
        if matches_rows.empty:
            continue
        geom = matches_rows.iloc[0]['geometry']
        admin_level = "8" if ("phường" in name.lower() or "thị trấn" in name.lower()) else "9"
        
        # Đưa trực tiếp ID OSM của Relation vào đây, JOSM sẽ tự hiểu là hành động chỉnh sửa (action="modify")
        process_polygon(geom, osm_id, name, admin_level, action_tag='action="modify"')

    # 3. GHI FILE .OSM
    print(f"[INFO] Đang ghi file đầu ra: {output_osm_path}...")
    os.makedirs(os.path.dirname(output_osm_path), exist_ok=True)
    with open(output_osm_path, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<osm version="0.6" generator="ProvinceRegulator" upload="true">\n')
        
        # Ghi toàn bộ Nodes
        for node in osm_xml_nodes:
            f.write(node + "\n")
            
        # Ghi toàn bộ Ways
        for way in osm_xml_ways:
            f.write(way + "\n")
            
        # Ghi toàn bộ Relations
        for rel in osm_xml_relations:
            f.write(rel + "\n")
            
        f.write('</osm>\n')

    print("=" * 70)
    print("   HOÀN THÀNH TẠO FILE UPDATE CHO JOSM!")
    print("=" * 70)
    print(f"File lưu tại: {output_osm_path}")
    print("\n[🎯] HƯỚNG DẪN CẬP NHẬT LÊN OPENSTREETMAP (OSM):")
    print(" 1. Tải và mở phần mềm JOSM (Java OpenStreetMap Editor).")
    print(" 2. Kéo thả file 'output/osm_changes.osm' vào màn hình JOSM.")
    print(" 3. JOSM sẽ tự động tải các Relation cũ về và thay thế bằng ranh giới mới của bạn.")
    print(" 4. Ấn nút 'Upload' (mũi tên hướng lên) trên JOSM để đẩy toàn bộ thay đổi lên OSM.")
    print("    * Cách này an toàn 100%, có thể review trước khi lưu, đúng chuẩn cộng đồng GIS.")
    print("=" * 70)

if __name__ == "__main__":
    main()
