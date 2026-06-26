# Hướng dẫn chạy Hệ thống Đối soát Dữ liệu GIS (GIS Province Regulator)

Tài liệu này mô tả trình tự các bước từ đầu để đối soát ranh giới hành chính Việt Nam (giữa hệ thống Official và OpenStreetMap). Phiên bản này sử dụng **100% Python GeoPandas và công cụ Osmium**, hoàn toàn **không cần cài đặt Database (PostGIS)**.

## ⚙️ Giai đoạn 0: Chuẩn bị Môi trường
1. **Cài đặt thư viện Python:** 
   Bạn cần môi trường Python (ảo) và các thư viện không gian:
   ```bash
   pip install geopandas pandas shapely rich pyyaml
   ```
2. **Cài đặt Osmium (Dành cho WSL/Ubuntu):** 
   Hệ thống yêu cầu `osmium-tool` để trích xuất file `.osm.pbf` tốc độ cao. Mở WSL/Ubuntu và gõ:
   ```bash
   sudo apt-get update
   sudo apt-get install osmium-tool
   ```
3. **Chuẩn bị Dữ liệu OSM nền:** 
   Tải file dữ liệu OSM PBF (ví dụ: `vietnam-260601.osm.pbf`) và đặt vào thư mục `data_osm/`.

---

## ⬇️ Giai đoạn 1: Tải Dữ liệu Chính thức (Official Data)
Nếu bạn chưa có dữ liệu Official, chạy các script sau để kéo dữ liệu mới nhất về máy dạng GeoJSON (lưu tại `output/data/`):

1. **Tải danh mục hành chính dạng bảng:**
   ```bash
   python crawler/dvhc.py
   ```
2. **Tải bản đồ ranh giới hành chính (Polygon/GeoJSON):**
   ```bash
   python crawler/qgis.py
   ```
*(Lưu ý: Nếu bạn đã có sẵn file `Vietnam_Communes.geojson` trong `output/data/` thì có thể bỏ qua bước này).*

---

## 🚀 Giai đoạn 2: Chạy Core Logic Đối soát (Pipeline Mới)

Đây là khối óc của hệ thống, thực hiện Spatial Join in-memory siêu tốc. Bạn có thể chạy từng bước hoặc chạy tự động tất cả.

### Cách 1: Chạy tự động (Khuyên dùng)
Bạn chỉ cần mở Terminal (PowerShell/WSL) và chạy file Pipeline. Nó sẽ tự động gọi luồng kiểm tra dữ liệu, trích xuất OSM, so sánh không gian và phân tích thống kê:
```bash
python crawler/pipeline.py
```
*(Lưu ý: Mặc định trong code có thể đã tạm comment lệnh trích xuất PBF tự động để tránh treo máy, bạn có thể tự mở comment trong file `pipeline.py` nếu muốn tự động 100%).*

### Cách 2: Chạy tay từng bước (Dễ kiểm soát lỗi)
**Bước 2.1:** Trích xuất ranh giới hành chính từ PBF ra GeoJSON (Chạy trên WSL):
```bash
bash scripts/02_extract_osm.sh
```
**Bước 2.2:** Thực hiện kiểm tra tính hợp lệ của file gốc:
```bash
python crawler/importer.py
```
**Bước 2.3:** Tính toán Spatial Join (So sánh tọa độ):
```bash
python crawler/compare.py
```
**Bước 2.4:** Tính toán báo cáo và xuất File thống kê:
```bash
python crawler/stats_analyzer.py
```

---

## 💾 File Đầu ra (Outputs)
Sau khi chạy xong, bạn sẽ thu được các file sau trong thư mục `output/data/`:
- **`osm_admin.geojson`**: File ranh giới lọc ra từ bản đồ OSM gốc.
- **`matched_compare.geojson`**: File hình học (chứa phần diện tích ranh giới bị rách/lệch giữa OSM và Official). Mở bằng QGIS để xem trực tiếp.
- **`matched_stats.csv`**: Bảng Excel chi tiết diện tích giao nhau và phần chênh lệch của từng Xã/Phường.
- **`review_candidates.csv`**: Danh sách các xã có trong hệ thống Official nhưng KHÔNG thể tìm thấy trên OSM.
- **`statistics.json` / `statistics.html`**: Báo cáo tổng kết tỷ lệ trùng khớp (Perfect Match, Missing, Difference).

---

## 🖥️ Giai đoạn 3: Trực quan hoá Kết Quả (Tuỳ chọn)

1. **Sinh file báo cáo ranh giới (Candidates/Render):**
   ```bash
   python crawler/difference_renderer.py
   python crawler/normalize_candidate.py
   ```

2. **Dùng Web App Tương tác:**
   Khởi động Backend API (FastAPI):
   ```bash
   python crawler-map/backend/main.py
   ```
   Khởi động Frontend Web (React/Vite):
   ```bash
   cd crawler-map/web
   npm install
   npm run dev
   ```
   Truy cập Localhost để sử dụng WebGIS Dashboard và review các ranh giới bị lỗi trực tiếp trên giao diện.
