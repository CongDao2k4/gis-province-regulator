#!/bin/bash
set -e

# Đổi thư mục làm việc về thư mục gốc của project
cd "$(dirname "$0")/.."

INPUT_FILE="data_osm/vietnam-260601.osm.pbf"
FILTERED_FILE="data/raw_osm/tinh_osm_admin_filtered.osm.pbf"
GEOJSON_FILE="data/raw_osm/tinh_boundary.geojson"

# Tạo thư mục data/raw_osm nếu chưa có
mkdir -p data/raw_osm

echo "[INFO] Đang lọc dữ liệu hành chính Tỉnh & Quốc gia từ OSM PBF (Bước 1: Lấy boundary=administrative)..."
osmium tags-filter "$INPUT_FILE" boundary=administrative -o data/raw_osm/tinh_temp_admin.osm.pbf --overwrite

echo "[INFO] Đang lọc dữ liệu hành chính Tỉnh & Quốc gia từ OSM PBF (Bước 2: Lọc admin_level=2,4)..."
osmium tags-filter data/raw_osm/tinh_temp_admin.osm.pbf admin_level=2,4 -o "$FILTERED_FILE" --overwrite

# Xoá file tạm sau khi lọc xong
rm data/raw_osm/tinh_temp_admin.osm.pbf

echo "[INFO] Đang xuất dữ liệu Tỉnh & Quốc gia sang định dạng GeoJSON..."
osmium export "$FILTERED_FILE" -c config/osmium_export_admin.json -f geojson -o "$GEOJSON_FILE" --overwrite --geometry-types=polygon

echo "[INFO] Xong! Kết quả ranh giới Tỉnh & Quốc gia tại: $GEOJSON_FILE"
