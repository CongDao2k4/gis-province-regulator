import geopandas as gpd
from sqlalchemy import create_engine
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')


def mock_data():
    engine = create_engine('postgresql+psycopg://gisuser:gispassword@localhost:5432/gis')
    
    # Lấy 5 xã từ OSM làm mẫu
    sql = """
    SELECT osm_id, name as a03_ten, way as geometry
    FROM planet_osm_polygon 
    WHERE boundary='administrative' AND admin_level='8' AND name IS NOT NULL
    LIMIT 5
    """
    
    print("Đang lấy dữ liệu mẫu từ OSM...")
    gdf = gpd.read_postgis(sql, engine, geom_col='geometry')
    
    if gdf.empty:
        print("Không tìm thấy xã nào trong OSM.")
        return
        
    print(f"Đã lấy {len(gdf)} xã. Đang bóp méo hình học (Shift) để tạo giả lập sai lệch...")
    
    # Bóp méo hình học một chút (Dịch chuyển tọa độ)
    # Vì tọa độ đang ở EPSG:3857 (Spherical Mercator), dịch 1000 mét
    if gdf.crs is None:
        gdf.set_crs(epsg=3857, inplace=True)
        
    # Translate geometry by 500 meters to create an artificial 'Difference'
    gdf['geometry'] = gdf['geometry'].translate(xoff=500, yoff=500)
    
    # Chuyển về EPSG:4326 theo chuẩn GeoJSON
    gdf.to_crs(epsg=4326, inplace=True)
    
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "output", "data")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "Vietnam.geojson")
    
    gdf.to_file(out_path, driver="GeoJSON")
    print(f"Đã tạo file {out_path} thành công!")

if __name__ == "__main__":
    mock_data()
