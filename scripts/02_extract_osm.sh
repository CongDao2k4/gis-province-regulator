#!/bin/bash
set -e

# Đổi thư mục làm việc về thư mục gốc của project
cd "$(dirname "$0")/.."

INPUT_FILE="data_osm/vietnam-260601.osm.pbf"
FILTERED_FILE="data/osm/osm_admin_filtered.osm.pbf"
GEOJSON_FILE="data/osm/boundary.geojson"

# Tạo thư mục data/osm nếu chưa có
mkdir -p data/osm

echo "[INFO] Đang lọc dữ liệu hành chính từ OSM PBF (Bước 1: Lấy boundary=administrative)..."
osmium tags-filter "$INPUT_FILE" boundary=administrative -o data/osm/temp_admin.osm.pbf --overwrite

echo "[INFO] Đang lọc dữ liệu hành chính từ OSM PBF (Bước 2: Lọc tiếp admin_level=4,5,6,7,8)..."
osmium tags-filter data/osm/temp_admin.osm.pbf admin_level=4,5,6,7,8 -o "$FILTERED_FILE" --overwrite

# Xoá file tạm sau khi lọc xong
rm data/osm/temp_admin.osm.pbf

echo "[INFO] Đang xuất dữ liệu sang định dạng GeoJSON..."
# Sử dụng cấu hình JSON để quyết định giữ lại tags nào, và chỉ xuất dạng Polygon
osmium export "$FILTERED_FILE" -c config/osmium_export_admin.json -f geojson -o "$GEOJSON_FILE" --overwrite --geometry-types=polygon

echo "[INFO] Xong! Kết quả tại: $GEOJSON_FILE"
