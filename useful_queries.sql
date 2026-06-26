-- =====================================================================
-- BỘ TRUY VẤN POSTGIS CHO DỰ ÁN WEBGIS CRAWLER (SAU SÁT NHẬP)
-- Mục tiêu: So sánh dữ liệu ranh giới Nhà nước (official_boundary)
-- với dữ liệu OSM (planet_osm_polygon) theo từng cấp Hành chính:
--   - Cấp Tỉnh / Thành phố: admin_level = '4'
--   - Cấp Quận / Huyện: admin_level = '6'
--   - Cấp Phường / Xã: admin_level = '8'
-- =====================================================================

-- LƯU Ý QUAN TRỌNG:
-- Bạn cần thêm điều kiện lọc theo admin_level tương ứng với lớp dữ liệu
-- Nhà nước mà bạn đang so sánh để tránh so sánh chéo (VD: So sánh Xã với Tỉnh).

-- ---------------------------------------------------------------------
-- 1. TRUY VẤN RENDER BẢN ĐỒ SAI LỆCH (Cho cấp XÃ - admin_level = '8')
-- Tách phần dư OSM (Đỏ), dư Official (Xanh), và giao (Vàng)
-- ---------------------------------------------------------------------
WITH osm_poly AS (
    SELECT osm_id, boundary, admin_level, ST_Transform(way, 4326) AS way 
    FROM planet_osm_polygon 
    WHERE boundary='administrative' AND admin_level='8' -- ĐỔI THÀNH '6' CHO HUYỆN, '4' CHO TỈNH
),
match AS (
    SELECT 
        o.a03_ten AS official_id,
        p.osm_id,
        -- Phần đa giác chỉ có trong OSM (Màu đỏ)
        ST_Difference(p.way, o.geometry) AS osm_only_geom,
        -- Phần đa giác chỉ có trong dữ liệu Official (Màu xanh)
        ST_Difference(o.geometry, p.way) AS off_only_geom,
        -- Phần đa giác chồng lấp (Màu vàng)
        ST_Intersection(o.geometry, p.way) AS overlap_geom,
        -- Tỷ lệ chồng lấp (0 -> 1)
        ST_Area(ST_Intersection(o.geometry, p.way)::geography)/GREATEST(ST_Area(o.geometry::geography), 1) AS overlap_ratio
    FROM official_boundary o
    JOIN osm_poly p ON ST_Intersects(o.geometry, p.way)
    -- Giả sử official_boundary có cột 'cap_hanh_chinh' = 'Xa'
),
best_match AS (
    -- Lấy ra polygon OSM khớp nhất với polygon Official
    SELECT *, ROW_NUMBER() OVER (PARTITION BY official_id ORDER BY overlap_ratio DESC) as rn 
    FROM match
)
SELECT * FROM best_match WHERE rn = 1;


-- ---------------------------------------------------------------------
-- 2. TRUY VẤN ỨNG VIÊN CẬP NHẬT TÊN / HÌNH HỌC (Cho cấp HUYỆN - admin_level = '6')
-- ---------------------------------------------------------------------
WITH osm_poly AS (
    SELECT osm_id, name, boundary, ST_Transform(way, 4326) AS way 
    FROM planet_osm_polygon 
    WHERE boundary='administrative' AND admin_level='6' -- Cấp Huyện
),
match AS (
    SELECT 
        o.a03_ten AS official_id,
        o.a03_ten AS off_name,
        p.osm_id,
        p.name AS osm_name,
        ST_Area(ST_Intersection(o.geometry, p.way)::geography)/GREATEST(ST_Area(o.geometry::geography), 1) AS overlap_ratio,
        ST_AsGeoJSON(o.geometry) AS off_geom
    FROM official_boundary o
    JOIN osm_poly p ON ST_Intersects(o.geometry, p.way)
),
best_match AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY official_id ORDER BY overlap_ratio DESC) as rn 
    FROM match
)
SELECT * FROM best_match 
WHERE rn = 1 
  -- Cảnh báo nếu sai khác diện tích > 2% HOẶC sai lệch tên gọi
  AND (overlap_ratio < 0.98 OR off_name != osm_name);


-- ---------------------------------------------------------------------
-- 3. TRUY VẤN THỐNG KÊ CHI TIẾT (Cho cấp TỈNH/THÀNH PHỐ - admin_level = '4')
-- Đo khoảng cách Hausdorff & Frechet giữa ranh giới cũ và mới
-- ---------------------------------------------------------------------
WITH osm_poly AS (
    SELECT osm_id, name, boundary, admin_level, ST_Transform(way, 4326) AS way 
    FROM planet_osm_polygon 
    WHERE boundary='administrative' AND admin_level='4' -- Cấp Tỉnh/Thành phố
),
overlap_data AS (
    SELECT 
        o.a03_ten AS official_id,
        p.osm_id,
        p.name AS osm_name,
        ST_Area(o.geometry::geography) AS off_area,
        ST_Area(p.way::geography) AS osm_area,
        ST_Area(ST_Intersection(o.geometry, p.way)::geography) AS intersect_area,
        ST_Area(ST_Difference(o.geometry, p.way)::geography) AS area_diff,
        -- Khoảng cách Hausdorff (đo độ chênh lệch biên cực đại)
        ST_HausdorffDistance(o.geometry, p.way) AS hausdorff,
        -- Khoảng cách dịch chuyển của tâm (Centroid)
        ST_Distance(ST_Centroid(o.geometry)::geography, ST_Centroid(p.way)::geography) AS centroid_diff,
        -- Chênh lệch chu vi
        ST_Length(ST_Difference(ST_Boundary(o.geometry), ST_Boundary(p.way))::geography) AS boundary_diff
    FROM official_boundary o
    LEFT JOIN osm_poly p ON ST_Intersects(o.geometry, p.way)
),
ranked AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY official_id ORDER BY intersect_area DESC) as rn 
    FROM overlap_data
)
SELECT * FROM ranked WHERE rn = 1;


-- ---------------------------------------------------------------------
-- 4. TRUY VẤN TÌM CÁC ĐƠN VỊ HÀNH CHÍNH "THIẾU" HOẶC "ĐÃ BỊ XÓA SAU SÁT NHẬP"
-- Ví dụ: Xã A (OSM) không còn tồn tại trong bản đồ mới
-- ---------------------------------------------------------------------
SELECT 
    p.osm_id, 
    p.name AS osm_name,
    p.admin_level
FROM (
    SELECT osm_id, name, admin_level, ST_Transform(way, 4326) as way 
    FROM planet_osm_polygon 
    WHERE boundary='administrative' 
      AND admin_level IN ('4', '6', '8') -- Quét cả 3 cấp Tỉnh, Huyện, Xã
) p
WHERE NOT EXISTS (
    SELECT 1 FROM official_boundary o 
    WHERE ST_Intersects(o.geometry, p.way) 
    -- Tính là vẫn tồn tại nếu có một vùng Official đè lên ít nhất 50% diện tích OSM
    AND ST_Area(ST_Intersection(o.geometry, p.way)::geography)/GREATEST(ST_Area(p.way::geography), 1) > 0.5
);
