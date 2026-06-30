import os
import sys
import json
import geopandas as gpd
from shapely.ops import unary_union

from rich.console import Console

console = Console()

def main():
    # Force UTF-8 stdout encoding for Windows compatibility
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8')
        
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    boundary_path = os.path.join(root_dir, "data", "raw_official", "boundary.geojson")
    boundary_out_path = os.path.join(root_dir, "data", "official", "boundary.geojson")
    
    console.print("=" * 70)
    console.print("\n[bold green]   CÔNG CỤ XỬ LÝ LỌC TRÙNG VÀ GỘP RANH GIỚI HÀNH CHÍNH (OFFICIAL DATA)[/bold green]")
    console.print("=" * 70)
    
    if not os.path.exists(boundary_path):
        console.print(f"\n[bold red][!] Không tìm thấy file dữ liệu: {boundary_path}[/bold red]")
        return
        
    console.print(f"\n[bold green] Đang tải dữ liệu từ: {boundary_path} ...[/bold green]")
    gdf = gpd.read_file(boundary_path)
    console.print(f"\n[bold green] Đã tải thành công: {len(gdf)} features.[/bold green]")
    
    # 1. Tìm các phần tử trùng lặp a02_xa
    # Lọc bỏ các giá trị a02_xa là None/Null/Trống trước khi tìm trùng
    valid_gdf = gdf[gdf['a02_xa'].notna() & (gdf['a02_xa'] != '')]
    duplicates = valid_gdf[valid_gdf.duplicated(subset=['a02_xa'], keep=False)]
    
    if duplicates.empty:
        console.print("\n[bold green] Không phát hiện bất kỳ xã/phường nào trùng mã 'a02_xa'. Dữ liệu đã sạch![/bold green]")
        return
        
    console.print(f"\n[bold orange] PHÁT HIỆN CÁC XÃ/PHƯỜNG TRÙNG MÃ 'a02_xa':[/bold orange]")
    console.print("-" * 70)
    
    grouped = duplicates.groupby('a02_xa')
    for a02_xa, group in grouped:
        ids = group['id'].tolist()
        names = group['a03_ten'].tolist()
        provinces = group['a04_tentinh'].tolist()
        target_id = ids[0]
        
        console.print(f"Xã/Phường: {names[0]} ({provinces[0]})")
        console.print(f" - Mã a02_xa chung: {a02_xa}")
        console.print(f" - Danh sách ID bị trùng: {ids}")
        console.print(f" ==> Sẽ gộp các geometry này vào mục tiêu ID: {target_id}")
        console.print("-" * 70)
        
    # 2. Thực hiện gộp (dissolve) dữ liệu dựa trên a02_xa
    # Dissolve kết hợp hình học (unary_union) và lấy thuộc tính 'first' cho các cột khác
    console.print("\n[bold green] Đang tiến hành gộp hình học (unary_union)...[/bold green]")
    gdf_clean = gdf.dissolve(by='a02_xa', aggfunc='first', as_index=False)
    
    # Đảm bảo cột 'id' vẫn nằm trong DataFrame sạch
    # dissolve giữ cột đầu tiên. Sắp xếp lại thứ tự cột cho giống file gốc
    columns_order = [c for c in gdf.columns if c != 'geometry'] + ['geometry']
    gdf_clean = gdf_clean[columns_order]
    
    console.print(f"\n[bold green] Gộp thành công! Số lượng features sau khi gộp: {len(gdf_clean)} (Giảm {len(gdf) - len(gdf_clean)} features).[/bold green]")
    
    # 3. Ghi lại dữ liệu dưới dạng GeoJSON với cấu trúc id ở gốc (Feature ID)
    console.print(f"\n[bold green] Đang lưu dữ liệu đã gộp về: {boundary_out_path} ...[/bold green]")
    
    # Convert sang dict GeoJSON để chỉnh sửa cấu trúc 'id' ở mức Feature Level
    geojson_data = json.loads(gdf_clean.to_json(drop_id=False))
    
    for feature in geojson_data.get('features', []):
        props = feature.get('properties', {})
        if 'id' in props:
            # Gán id lên root level của Feature để giữ nguyên cấu trúc chuẩn
            feature['id'] = props['id']
            # Xóa id khỏi properties để cấu trúc dữ liệu y như bản cũ
            del props['id']
            
    with open(boundary_out_path, 'w', encoding='utf-8') as f:
        json.dump(geojson_data, f, ensure_ascii=False, indent=2)
        
    console.print("\n[bold green] Hoàn thành lưu trữ dữ liệu sạch![/bold green]")
    console.print("=" * 70)

if __name__ == "__main__":
    main()
