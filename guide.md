# Hướng dẫn Vận hành Hệ thống Đối soát & Cập nhật Ranh giới Hành chính (GIS Province Regulator)

Tài liệu này hướng dẫn chi tiết cách cài đặt môi trường, cách chạy hệ thống đối soát ranh giới hành chính Việt Nam (giữa dữ liệu của Nhà nước - Official và dữ liệu OpenStreetMap - OSM), và cách xem số liệu kết quả để thực hiện chỉnh sửa dữ liệu (sửa, xóa, thêm mới) trên OSM.

---

## ⚙️ Giai đoạn 0: Chuẩn bị Môi trường & Dữ liệu

### 1. Cài đặt môi trường ảo Python và thư viện:
Bạn cần môi trường Python và các thư viện xử lý dữ liệu không gian.
```powershell
# Tạo môi trường ảo
python -m venv .venv
.venv\Scripts\activate

# Cài đặt thư viện
pip install geopandas pandas shapely matplotlib rapidfuzz openpyxl rich pyyaml
```

### 2. Cài đặt Osmium Tool (Yêu cầu trên WSL / Ubuntu):
Hệ thống dùng `osmium-tool` để trích lọc dữ liệu OSM `.osm.pbf` thô với tốc độ cao.
```bash
sudo apt-get update
sudo apt-get install osmium-tool
```

### 3. Chuẩn bị dữ liệu OSM nền:
Tải file dữ liệu OSM PBF Việt Nam (ví dụ từ Geofabrik: `vietnam-latest.osm.pbf`), đặt vào thư mục dự án và đổi tên thành `data/osm/vietnam.osm.pbf`.

---

## 📂 Vai trò của từng File trong dự án

Để thuận tiện cho việc chỉnh sửa và bảo trì mã nguồn sau này, dưới đây là vai trò chi tiết của từng file trong thư mục `src/` và `scripts/`:

### 🛠️ Thư mục `src/` (Mã nguồn lõi đối soát):
1.  **[src/loader.py](file:///d:/A-VinVSF/gis-province-regulator/src/loader.py)**: Bộ nạp dữ liệu GeoJSON. Có vai trò đọc file ranh giới, tự động kiểm tra tính hợp lệ của đa giác hình học, sửa các lỗi đa giác rách/hở bằng `make_valid()`, và tạo chỉ mục không gian (spatial index) để tối ưu tốc độ truy vấn.
2.  **[src/matcher.py](file:///d:/A-VinVSF/gis-province-regulator/src/matcher.py)**: Bộ so khớp ranh giới. Có vai trò chuyển hệ chiếu phẳng UTM 48N (`EPSG:32648`) để tính diện tích thực chuẩn xác. Thực hiện so khớp vị trí không gian (Spatial Join) kết hợp so khớp ngữ nghĩa tên gọi (Fuzzy Ratio). Áp dụng quy tắc lọc chênh lệch (nếu tên khác nhau quá nhiều và tỷ lệ đè thấp thì từ chối khớp) để loại bỏ hoàn toàn lỗi khớp nhầm xã thiếu vào huyện bao quanh.
3.  **[src/compare.py](file:///d:/A-VinVSF/gis-province-regulator/src/compare.py)**: Bộ so sánh hình học. Có vai trò tính toán phần giao (Intersection) và phần chênh lệch (Difference) của các cặp khớp. Xác định chi tiết chênh lệch diện tích (m²), khoảng cách Hausdorff và trích xuất các đa giác thừa (OSM thừa ranh giới - red) và đa giác thiếu (OSM thiếu ranh giới - blue) ra file `difference.geojson`.
4.  **[src/stats.py](file:///d:/A-VinVSF/gis-province-regulator/src/stats.py)**: Bộ sinh thống kê. Có vai trò tổng hợp số liệu kết quả, vẽ biểu đồ phân phối tỉ lệ trùng khớp ranh giới, và xuất các báo cáo thống kê trực quan dạng HTML tiếng Việt, Excel và JSON.
5.  **[src/candidate.py](file:///d:/A-VinVSF/gis-province-regulator/src/candidate.py)**: Bộ phân loại ứng viên. Có vai trò gom kết quả từ bước so sánh ranh giới và danh sách xã thiếu/xã thừa, phân chia chúng thành 3 hành động cụ thể trên OSM: Sửa ranh giới lệch (`Need Update`), Thêm ranh giới thiếu (`Missing`), và Xóa ranh giới thừa (`New`).
6.  **[src/pipeline.py](file:///d:/A-VinVSF/gis-province-regulator/src/pipeline.py)**: Bộ điều phối trung tâm. Có vai trò liên kết tuần tự các module trên lại với nhau thành một luồng chạy khép kín từ đầu đến cuối.

### 📜 Thư mục `scripts/` (Kịch bản bổ trợ & Truy vấn):
1.  **[scripts/02_extract_osm.sh](file:///d:/A-VinVSF/gis-province-regulator/scripts/02_extract_osm.sh)**: Script bash chạy trên WSL để gọi công cụ Osmium lọc và trích xuất dữ liệu ranh giới hành chính từ cấp tỉnh đến xã (`admin_level=4,5,6,7,8,9`) từ file PBF thô của OSM sang định dạng GeoJSON gọn nhẹ phục vụ đối soát.
2.  **[scripts/inspect_results.py](file:///d:/A-VinVSF/gis-province-regulator/scripts/inspect_results.py)**: Script truy vấn nhanh. Có vai trò đọc kết quả đối soát cuối cùng, in ra màn hình danh sách chi tiết các xã thiếu, các xã lệch ranh giới nhiều nhất và các vùng thừa trên OSM kèm đường link trực tiếp đến Relation đó trên OpenStreetMap để sửa nhanh.
3.  **[scripts/generate_osm_changes.py](file:///d:/A-VinVSF/gis-province-regulator/scripts/generate_osm_changes.py)**: Bộ sinh file cập nhật OSM. Có vai trò đọc ranh giới chuẩn từ dữ liệu Official, chuyển đổi tọa độ địa lý và hình học đa giác thành cấu trúc file OSM XML (`.osm`) chuẩn hóa JOSM để tự động sửa hoặc vẽ mới hàng loạt trên OpenStreetMap.

---

## 🚀 Giai đoạn 2: Chạy Đối soát (Matching Pipeline)

Hệ thống hỗ trợ **Chạy tự động tổng thể bằng 1 lệnh duy nhất** hoặc **Chạy thủ công riêng lẻ từng bước** để debug dữ liệu.

### Cách 1: Chạy tổng thể (Khuyến khích)
Chạy toàn bộ quy trình tải, lọc, đơn giản hóa hình học hiển thị, so khớp không gian và tính toán sai lệch ranh giới:
```powershell
.venv\Scripts\python.exe src/pipeline.py
```

### Cách 2: Chạy riêng lẻ từng bước (Step-by-step)
Nếu bạn muốn kiểm tra trung gian hoặc sửa đổi dữ liệu từng phần, bạn có thể chạy tuần tự:
```powershell
.venv\Scripts\python.exe src/matcher.py
.venv\Scripts\python.exe src/compare.py
.venv\Scripts\python.exe src/stats.py
.venv\Scripts\python.exe src/candidate.py
```

---

## 📊 Giai đoạn 3: Hướng dẫn Quy trình sửa đổi Bản đồ OSM

Dữ liệu đối soát và giao diện WebGIS phân loại các xã thành **4 danh mục cụ thể**: **Sửa ranh giới lệch, Thêm ranh giới thiếu, Xóa ranh giới thừa, và các xã đã Khớp hoàn hảo.** Dưới đây là hướng dẫn quy trình sửa đổi chi tiết cho từng nhóm bằng công cụ JOSM (Java OpenStreetMap Editor):

### 📥 1. Chuẩn bị JOSM:
1. Tải và cài đặt phần mềm biên tập **JOSM** tại: [https://josm.openstreetmap.org/](https://josm.openstreetmap.org/).
2. Mở JOSM lên, vào phần **Settings (F12)** -> Chọn tab **Connection settings** -> Nhập tài khoản và mật khẩu tài khoản OpenStreetMap của bạn để cấp quyền upload thay đổi.

### ⚠️ 2. Quy trình Sửa ranh giới lệch (Need Update)
*Hiện trạng:* Xã đã tồn tại trên OSM nhưng hình học ranh giới bị lệch, lấn chiếm hoặc méo mó so với dữ liệu chuẩn của Nhà nước.
1.  Chạy script tạo file XML cập nhật:
    ```powershell
    .venv\Scripts\python.exe scripts/generate_osm_changes.py
    ```
2.  Kéo thả file kết quả [output/osm_changes.osm](file:///d:/A-VinVSF/gis-province-regulator/output/osm_changes.osm) vào màn hình làm việc JOSM.
3.  JOSM sẽ tự động tải các Relation xã cũ bị lệch từ server OSM về máy của bạn và đè đa giác ranh giới chuẩn lên.
4.  **Kiểm tra và sửa biên giới chung (Shared Borders):**
    *   Trong OSM, ranh giới xã thường dùng chung đường bao (ways) với các xã lân cận.
    *   Hãy bật lớp ảnh vệ tinh làm nền để kiểm tra trực quan ranh giới chuẩn.
    *   Nếu đa giác mới làm lệch biên giới chung với các xã chưa đối soát xung quanh, sử dụng phím tắt **`M` (Merge)** trong JOSM để gộp các điểm biên giới chung lại với nhau một cách mượt mà, đảm bảo ranh giới khép kín và không bị đứt đoạn.
5.  Ấn nút **Upload (mũi tên hướng lên)** trên JOSM để gửi cập nhật lên server OSM.

### ❌ 3. Quy trình Thêm ranh giới thiếu (Missing)
*Hiện trạng:* Xã có trong dữ liệu Nhà nước nhưng hoàn toàn chưa có vùng đa giác nào tương đương trên OSM (ví dụ: Phường Vân Sơn, Đặc khu Hoàng Sa, Đặc khu Trường Sa).
1.  Sau khi chạy `generate_osm_changes.py`, đa giác chuẩn của các xã thiếu này đã được tự động định cấu hình là các Relation tạo mới với **ID âm** (ví dụ: relation `-1001`).
2.  Khi bạn kéo file `osm_changes.osm` vào JOSM, JOSM sẽ tự động vẽ đa giác khép kín này lên bản đồ kèm theo các thẻ tag hành chính chuẩn Việt Nam được gán tự động.
3.  Bạn chỉ cần nhấn nút **Upload** trên JOSM. Server OSM sẽ tự nhận dạng ID âm này và sinh ra ID dương thực tế mới trên cơ sở dữ liệu toàn cầu.

### 🗑️ 4. Quy trình Xóa ranh giới thừa trên OSM (New / Candidates for Deletion)
*Hiện trạng:* Các ranh giới xã cũ hoặc các đa giác vẽ lỗi trên OSM bị thừa, không khớp với bất kỳ đơn vị hành chính chính thức nào của Nhà nước.
1.  Chạy script truy vấn nhanh:
    ```powershell
    .venv\Scripts\python.exe scripts/inspect_results.py
    ```
    *Script này sẽ in ra danh sách các Relation ID thừa trên OSM kèm đường link trực tiếp.*
2.  Với mỗi vùng thừa, click vào link OSM để xem thông tin trực quan hoặc dùng chức năng **Download Object** (Ctrl + Shift + D) trong JOSM, nhập loại là `relation` và điền ID thừa đó vào để tải về máy.
3.  **Hành động xóa/gộp:**
    *   Nếu đó là ranh giới cũ đã sáp nhập (ví dụ: Xã A đã sáp nhập vào Xã B): Hãy chọn Relation đó trong JOSM, click chuột phải chọn **Delete** để xóa Relation ranh giới cũ đi.
    *   Nếu đa giác OSM đó chứa dữ liệu dân cư hoặc địa danh lịch sử quan trọng, hãy gộp chúng vào Relation của xã mới thay vì xóa hẳn.
4.  Nhấn **Upload** trên JOSM để xác nhận xóa thực thể ranh giới thừa khỏi bản đồ thế giới.

---

## 📡 Giai đoạn 4: Vận hành REST API & Đồng bộ hóa Tức thời (Hot Sync API)

Dự án hỗ trợ một máy chủ WebGIS REST API cùng các script bổ trợ mới giúp đồng bộ hóa trực tiếp các quyết định biên tập từ giao diện WebGIS xuống cơ sở dữ liệu GeoJSON và chuẩn bị dữ liệu cho JOSM XML.

### 🛠️ Các File Code mới và Vai trò:
1.  **[crawler/resolve_duplicates.py](file:///d:/A-VinVSF/gis-province-regulator/crawler/resolve_duplicates.py)** (Công cụ dọn dẹp trùng lặp):
    *   *Vai trò:* Phát hiện và tự động gộp (dissolve) hình học của các xã/phường có cùng mã hành chính `a02_xa` nhưng bị chia tách thành nhiều ID khác nhau (ví dụ: các xã vùng đảo Bắc Cam Ranh bị phân rã thành nhiều polygon đảo rời rạc).
    *   *Cách chạy:*
        ```powershell
        .venv\Scripts\python.exe crawler/resolve_duplicates.py
        ```
2.  **[scripts/apply_osm_edit.py](file:///d:/A-VinVSF/gis-province-regulator/scripts/apply_osm_edit.py)** (Bộ áp dụng thay đổi và tạo JOSM XML):
    *   *Vai trò:* Áp dụng các thay đổi ranh giới trực tiếp vào tệp GeoJSON gốc của OSM (`data/osm/boundary.geojson`), tự động cập nhật ranh giới WebGIS đơn giản hóa, chuyển trạng thái xã trong `candidate.json` thành `"Matched"` và ghi nhận tích lũy các thay đổi này thành file cập nhật JOSM XML (`output/osm_changes.osm`). Có thể chạy độc lập qua CLI để kiểm thử nhanh.
    *   *Cách chạy CLI:*
        ```powershell
        # Thao tác SỬA ranh giới (Update)
        .venv\Scripts\python.exe scripts/apply_osm_edit.py --action update --official_id <official_id> --osm_id <osm_id>
        
        # Thao tác THÊM ranh giới (Create)
        .venv\Scripts\python.exe scripts/apply_osm_edit.py --action create --official_id <official_id>
        
        # Thao tác XÓA ranh giới thừa (Delete)
        .venv\Scripts\python.exe scripts/apply_osm_edit.py --action delete --osm_id <osm_id>
        ```
3.  **[crawler-map/backend/main.py](file:///d:/A-VinVSF/gis-province-regulator/crawler-map/backend/main.py)** (REST API Backend Server):
    *   *Vai trò:* Cung cấp các REST API endpoints phục vụ WebGIS. Tích hợp endpoint `/api/edit-osm` gọi trực tiếp đến module `apply_edit` của script trên, đồng thời có cơ chế **Hot Reload Cache** tự động nạp lại bộ đệm RAM để thay đổi được hiển thị tức thời trên bản đồ WebGIS ngay khi người dùng nhấn nút thao tác mà không cần khởi động lại Server API.
    *   *Cách chạy:*
        ```powershell
        .venv\Scripts\python.exe crawler-map/backend/main.py
        ```

### 📡 Danh sách REST API Endpoints hỗ trợ:

| Method | Endpoint | Tham số | Mô tả |
| :--- | :--- | :--- | :--- |
| `GET` | `/statistics` | Không | Lấy tóm tắt thống kê đối soát của dự án (Perfect Match, Changed, Missing, New). |
| `GET` | `/candidates/metadata` | Không | Lấy danh sách nhẹ (không chứa hình học) của các commune sai lệch (Missing, Need Update, New) để hiển thị danh sách cuộn nhanh trên sidebar. |
| `GET` | `/candidate/{official_id}/geometry` | `osm_id` | Lấy đầy đủ hình học của xã Official, xã OSM và các vùng sai lệch (difference) tương ứng để vẽ chi tiết lên bản đồ khi click. |
| `GET` | `/official/communes` | Không | Tải về toàn bộ ranh giới đơn giản hóa của các xã Official (dùng để vẽ nền). |
| `GET` | `/osm/communes` | Không | Tải về toàn bộ ranh giới đơn giản hóa của các xã OSM hiện tại (dùng để vẽ nền). |
| `GET` | `/difference` | Không | Tải về toàn bộ đa giác chênh lệch ranh giới hành chính. |
| `GET` | `/missing` | Không | Tải về toàn bộ ranh giới các xã bị thiếu trên OSM. |
| `GET` | `/new` | Không | Tải về toàn bộ ranh giới các vùng thừa trên OSM. |
| `GET` | `/compare-results` | Không | Lấy thông tin so sánh chi tiết dạng mảng JSON (Overlap ratio, IoU, Hausdorff distance, name similarity) cho biểu đồ thống kê. |
| `GET` | `/search` | `q` (từ khóa) | Tìm kiếm xã/phường theo tên bằng giải thuật Fuzzy Match trên RAM với tốc độ phản hồi cực nhanh. |
| `POST` | `/api/edit-osm` | Body: `{official_id, osm_id, action}` | Đồng bộ hóa quyết định chỉnh sửa (update/modify/create/delete) trực tiếp xuống GeoJSON, JOSM XML và cập nhật nóng bộ nhớ RAM. |

---

## 🗺️ Giai đoạn 3: Đối soát cấp Tỉnh & Biên giới Quốc gia Việt Nam (Mới)

Để chạy luồng đối soát và chỉnh sửa ranh giới cấp Tỉnh (`admin_level=4`) và Biên giới Việt Nam (`admin_level=2`), các bước thực hiện như sau:

### ⚙️ Hướng dẫn vận hành bằng dòng lệnh (CLI)

1.  **Trích xuất dữ liệu OSM cấp Tỉnh và Quốc gia:**
    Đầu tiên, chạy script để lọc riêng `admin_level=2,4` từ file PBF gốc sang tệp GeoJSON độc lập:
    ```bash
    bash scripts/02_extract_osm_tinh.sh
    ```
    *Kết quả đầu ra:* `data/osm/tinh_boundary.geojson`

2.  **Chạy Pipeline đối soát cấp Tỉnh & Quốc gia:**
    Pipeline này sẽ tự động tải ranh giới tỉnh gốc, tự động gộp (dissolve) các tỉnh để tạo ranh giới quốc gia Việt Nam ảo làm nguồn đối soát chính thức cho biên giới quốc gia, sau đó so sánh không gian và phân loại:
    ```powershell
    .venv\Scripts\python.exe src/tinh_pipeline.py
    ```
    *Các tệp kết quả sẽ được sinh ra độc lập tại:*
    *   Thư mục so sánh: `output/tinh_comparison/` (`difference.geojson`, `missing.geojson`, `new.geojson`, `compare_result.json`)
    *   Thư mục ứng viên: `output/tinh_candidates/` (`candidate.json`)
    *   Thư mục thống kê: `output/tinh_statistics/` (`statistics.json`, `statistics.html`, biểu đồ...)

3.  **Cập nhật / Đồng bộ ranh giới Tỉnh qua CLI:**
    Sử dụng tệp `scripts/apply_tinh_edit.py` để đồng bộ ranh giới:
    ```powershell
    # Đồng bộ sửa đổi ranh giới tỉnh sang OSM GeoJSON & sinh JOSM XML
    .venv\Scripts\python.exe scripts/apply_tinh_edit.py --action update --official_id <official_id> --osm_id <osm_id>
    
    # Đồng bộ thêm mới tỉnh bị thiếu
    .venv\Scripts\python.exe scripts/apply_tinh_edit.py --action create --official_id <official_id>
    
    # Đồng bộ xóa tỉnh thừa khỏi OSM
    .venv\Scripts\python.exe scripts/apply_tinh_edit.py --action delete --osm_id <osm_id>
    ```

### 📡 Danh sách REST API Endpoints cấp Tỉnh:

Máy chủ API (`crawler-map/backend/main.py`) hỗ trợ song song các API cấp Tỉnh với tiền tố `/tinh/`:

| Method | Endpoint | Tham số | Mô tả |
| :--- | :--- | :--- | :--- |
| `GET` | `/tinh/statistics` | Không | Lấy tóm tắt thống kê đối soát cấp tỉnh & quốc gia. |
| `GET` | `/tinh/candidates/metadata` | Không | Lấy danh sách candidate cấp tỉnh lệch ranh giới/tên. |
| `GET` | `/tinh/candidate/{official_id}/geometry` | `osm_id` | Lấy chi tiết hình học của tỉnh Official, OSM và các vùng sai lệch tương ứng. |
| `GET` | `/tinh/official/provinces` | Không | Tải về ranh giới gốc của các tỉnh Official. |
| `GET` | `/tinh/osm/provinces` | Không | Tải về ranh giới của các tỉnh/quốc gia trên OSM. |
| `GET` | `/tinh/difference` | Không | Tải về toàn bộ đa giác chênh lệch ranh giới cấp tỉnh/quốc gia. |
| `GET` | `/tinh/missing` | Không | Tải về ranh giới các tỉnh/quốc gia bị thiếu trên OSM. |
| `GET` | `/tinh/new` | Không | Tải về ranh giới các tỉnh thừa trên OSM. |
| `GET` | `/tinh/compare-results` | Không | Lấy thông tin so khớp chi tiết dạng mảng JSON cho các biểu đồ. |
| `GET` | `/tinh/search` | `q` (từ khóa) | Tìm kiếm tỉnh/quốc gia theo tên. |
| `POST` | `/tinh/api/edit-tinh` | Body: `{official_id, osm_id, action}` | Tiếp nhận quyết định đồng bộ ranh giới tỉnh từ WebGIS và tự động cập nhật cache bộ nhớ RAM tức thời. |
