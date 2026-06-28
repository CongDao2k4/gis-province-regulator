import json
import os
import sys
import pandas as pd
import geopandas as gpd

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    # Thư mục chứa kết quả
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates_json_path = os.path.join(root_dir, "output", "candidates", "candidate.json")
    diff_geojson_path = os.path.join(root_dir, "output", "comparison", "difference.geojson")
    
    print("=" * 70)
    print("   CÔNG CỤ TRUY VẤN KẾT QUẢ ĐỐI SOÁT - PHỤC VỤ BIÊN TẬP / UPDATE OSM")
    print("=" * 70)
    
    if not os.path.exists(candidates_json_path):
        print("[!] Không tìm thấy file candidate.json. Hãy chạy 'python src/pipeline.py' trước!")
        return

    # 1. Đọc danh sách ứng viên (dạng bảng để dễ xử lý)
    df = pd.read_json(candidates_json_path)
    
    # 2. Lọc các xã THIẾU trên OSM (cần thêm mới)
    missing_df = df[df["category"] == "Missing"]
    print(f"\n[❌] DANH SÁCH XÃ THIẾU TRÊN OSM (Cần thêm mới vào OSM) - Tổng số: {len(missing_df)}")
    print("-" * 70)
    for idx, row in missing_df.iterrows():
        print(f" Official ID: {row['official_id']:<35} | Tên: {row['official_name']:<20} | Tỉnh: {row['province']}")
        # Mã osm_id lúc này là 'N/A' vì chưa tồn tại ranh giới trên OSM.
        
    # 3. Lọc các xã BỊ LỆCH ranh giới (Cần chỉnh sửa hình học trên OSM)
    # Lệch ranh giới khi ranh giới khớp tên nhưng diện tích chồng đè (overlap_ratio) nhỏ hơn 98%
    misaligned_df = df[(df["category"] == "Need Update") | 
                       ((df["category"] == "Need Review") & (df["osm_id"] != "N/A"))]
    
    # Sắp xếp theo tỷ lệ trùng khớp từ thấp đến cao để ưu tiên sửa xã lệch nhiều trước
    misaligned_df = misaligned_df.sort_values(by="overlap_ratio")
    
    print(f"\n[⚠️] DANH SÁCH XÃ BỊ LỆCH RANH GIỚI (Cần chỉnh sửa hình học trên OSM) - Tổng số: {len(misaligned_df)}")
    print("-" * 70)
    for idx, row in misaligned_df.head(15).iterrows():  # Hiện thị thử 15 xã lệch nhiều nhất
        print(f" OSM ID: {str(row['osm_id']):<12} | Tên Official: {row['official_name']:<20} | Tên OSM: {row['osm_name']:<20} | Trùng khớp: {row['overlap_ratio']*100:.1f}%")
        # Đường link dẫn thẳng tới Relation trên OSM để sửa:
        print(f"    -> Link OSM: https://www.openstreetmap.org/relation/{row['osm_id']}")
    
    if len(misaligned_df) > 15:
        print(f"    ... và {len(misaligned_df) - 15} xã khác bị lệch ranh giới.")

    # 3.5. Lọc các vùng thừa trên OSM cần xóa/gộp (category == "New")
    new_df = df[df["category"] == "New"]
    print(f"\n[🗑️] DANH SÁCH VÙNG THỪA CẦN XÓA/GỘP TRÊN OSM - Tổng số: {len(new_df)}")
    print("-" * 70)
    for idx, row in new_df.head(10).iterrows():  # Hiển thị thử 10 vùng thừa đầu tiên
        print(f" OSM ID: {str(row['osm_id']):<12} | Tên OSM: {row['osm_name']:<30} | Lý do: {row['reason']}")
        print(f"    -> Link OSM: https://www.openstreetmap.org/relation/{row['osm_id']}")
    if len(new_df) > 10:
        print(f"    ... và {len(new_df) - 10} vùng thừa khác cần xử lý.")

    # 4. Cách đọc các vùng đa giác bị lệch (diff geometry) để phục vụ code tự động cập nhật
    if os.path.exists(diff_geojson_path):
        print("\n[💎] HƯỚNG DẪN CODE ĐỌC ĐA GIÁC LỆCH RANH GIỚI (DIFFERENCE GEOMETRY):")
        print("-" * 70)
        print("Bạn có thể dùng GeoPandas đọc file 'output/comparison/difference.geojson' để lấy:")
        print(" - Các đa giác phần thừa OSM (fillColor: red) -> cần cắt bớt trên OSM.")
        print(" - Các đa giác phần thiếu OSM (fillColor: blue) -> cần bù thêm trên OSM.")
        print("\nVí dụ code Python:")
        print("""
        import geopandas as gpd
        
        # Đọc file ranh giới sai lệch
        diff_gdf = gpd.read_file('output/comparison/difference.geojson')
        
        # Lọc phần thừa của một xã cụ thể trên OSM (ví dụ xã có osm_id = '13455517')
        osm_excess = diff_gdf[(diff_gdf['osm_id'] == '13455517') & (diff_gdf['fillColor'] == 'red')]
        if not osm_excess.empty:
            print("Phần diện tích thừa cần cắt bỏ (Multipolygon):", osm_excess.iloc[0]['geometry'])
        """)
    print("=" * 70)

if __name__ == "__main__":
    main()
