import os
import sys
import json
import logging
import base64
import pandas as pd
import matplotlib
# Use Agg backend for matplotlib to avoid window opening issues in background tasks
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("stats")

class StatisticsGenerator:
    """
    Generates statistics reports:
    - Counts of Matched (Khớp), Missing (Cần thêm mới), Changed (Cần sửa), New (Cần xóa).
    - Ranking of differences.
    - Exports to CSV, Excel, JSON, and HTML.
    - Generates visual reports (Histogram & Pie Chart) and embeds them in HTML.
    """
    def __init__(self, compare_results: list, missing_count: int, new_count: int):
        self.df = pd.DataFrame(compare_results)
        self.missing_count = missing_count
        self.new_count = new_count

    def generate(self, output_dir: str):
        logger.info("Generating statistics and reports...")
        os.makedirs(output_dir, exist_ok=True)
        
        stats = {}
        
        # Classify matches in compare results
        # We categorize matched records into 'Perfect Match' (overlap >= 0.98) and 'Changed' (overlap < 0.98)
        if not self.df.empty:
            perfect_matches = self.df[self.df['overlap_ratio'] >= 0.98]
            changed = self.df[self.df['overlap_ratio'] < 0.98]
            
            stats["Summary"] = {
                "total_official": len(self.df) + self.missing_count,
                "total_matched": len(self.df),
                "perfect_match": len(perfect_matches),
                "need_update": len(changed),
                "need_add": self.missing_count,
                "need_delete": self.new_count
            }
        else:
            stats["Summary"] = {
                "total_official": self.missing_count,
                "total_matched": 0,
                "perfect_match": 0,
                "need_update": 0,
                "need_add": self.missing_count,
                "need_delete": self.new_count
            }

        # 1. Generate Matplotlib Charts
        hist_base64 = ""
        pie_base64 = ""
        
        try:
            # Histogram of Overlap Ratios
            if not self.df.empty:
                plt.figure(figsize=(6, 4))
                plt.hist(self.df['overlap_ratio'] * 100, bins=20, color='#3186cc', edgecolor='black', alpha=0.7)
                plt.title("Biểu đồ phân phối tỉ lệ trùng khớp (%)", fontsize=12, fontweight='bold')
                plt.xlabel("Tỉ lệ trùng khớp (%)", fontsize=10)
                plt.ylabel("Tần suất", fontsize=10)
                plt.grid(axis='y', linestyle='--', alpha=0.7)
                plt.tight_layout()
                
                hist_path = os.path.join(output_dir, "overlap_histogram.png")
                plt.savefig(hist_path, dpi=150)
                plt.close()
                
                with open(hist_path, "rb") as image_file:
                    hist_base64 = base64.b64encode(image_file.read()).decode('utf-8')
            
            # Pie Chart of Categories
            plt.figure(figsize=(6, 4))
            labels = ['Khớp hoàn hảo', 'Cần sửa ranh giới', 'Cần thêm mới', 'Cần xóa ở OSM']
            sizes = [
                stats["Summary"]["perfect_match"],
                stats["Summary"]["need_update"],
                stats["Summary"]["need_add"],
                stats["Summary"]["need_delete"]
            ]
            colors = ['#2ecc71', '#f1c40f', '#e74c3c', '#3498db']
            
            # Filter categories with 0 values to avoid messy pie chart
            pie_data = [(l, s, c) for l, s, c in zip(labels, sizes, colors) if s > 0]
            if pie_data:
                p_labels, p_sizes, p_colors = zip(*pie_data)
                plt.pie(p_sizes, labels=p_labels, colors=p_colors, autopct='%1.1f%%', startangle=140, 
                        textprops={'fontsize': 10})
                plt.title("Phân bổ kết quả đối soát ranh giới", fontsize=12, fontweight='bold')
                plt.tight_layout()
                
                pie_path = os.path.join(output_dir, "status_pie_chart.png")
                plt.savefig(pie_path, dpi=150)
                plt.close()
                
                with open(pie_path, "rb") as image_file:
                    pie_base64 = base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"Error generating charts: {e}")

        # 2. Get Top 100 Differences
        if not self.df.empty:
            top_diff = self.df.sort_values(by="area_difference_sqm", ascending=False).head(100)
        else:
            top_diff = pd.DataFrame()

        # 3. Export to CSV, Excel, JSON
        stats_json_path = os.path.join(output_dir, "statistics.json")
        with open(stats_json_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=4)
            
        top_csv_path = os.path.join(output_dir, "statistics.csv")
        top_diff.to_csv(top_csv_path, index=False, encoding="utf-8")
        
        top_xlsx_path = os.path.join(output_dir, "statistics.xlsx")
        try:
            top_diff.to_excel(top_xlsx_path, index=False)
            logger.info("Saved Excel report successfully.")
        except Exception as e:
            logger.warning(f"Could not save Excel file (missing openpyxl?): {e}")

        # 4. Export HTML Report (in Vietnamese)
        html_path = os.path.join(output_dir, "statistics.html")
        
        top_rows_html = ""
        if not top_diff.empty:
            for _, r in top_diff.iterrows():
                top_rows_html += f"""
                <tr>
                    <td>{r['official_id']}</td>
                    <td>{r['official_name']}</td>
                    <td>{r['province']}</td>
                    <td>{r['osm_id']}</td>
                    <td>{r['osm_name']}</td>
                    <td>{r['overlap_ratio']*100:.2f}%</td>
                    <td>{r['iou']*100:.2f}%</td>
                    <td>{r['area_difference_sqm']:,.1f}</td>
                    <td>{r['hausdorff']:,.2f}</td>
                </tr>
                """
        else:
            top_rows_html = "<tr><td colspan='9' style='text-align:center;'>Không tìm thấy xã nào có sai lệch.</td></tr>"

        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Báo cáo Thống kê Đối soát Ranh giới Hành chính GIS</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #f8f9fa;
            color: #333;
            margin: 0;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: #fff;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        h1, h2 {{
            color: #2c3e50;
            border-bottom: 2px solid #ecf0f1;
            padding-bottom: 10px;
        }}
        .summary-cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }}
        .card {{
            background-color: #f1f2f6;
            padding: 20px;
            border-radius: 6px;
            text-align: center;
            border-left: 5px solid #2980b9;
        }}
        .card.success {{ border-left-color: #2ecc71; }}
        .card.warning {{ border-left-color: #f1c40f; }}
        .card.danger {{ border-left-color: #e74c3c; }}
        .card-value {{
            font-size: 28px;
            font-weight: bold;
            color: #2c3e50;
            margin-top: 5px;
        }}
        .charts {{
            display: flex;
            flex-wrap: wrap;
            gap: 30px;
            justify-content: center;
            margin-bottom: 40px;
        }}
        .chart-container {{
            background: #fff;
            border: 1px solid #e1e8ed;
            border-radius: 6px;
            padding: 10px;
            text-align: center;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
            font-size: 14px;
        }}
        th, td {{
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #2c3e50;
            color: white;
            font-weight: bold;
        }}
        tr:hover {{ background-color: #f5f6fa; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Báo cáo Thống kê Đối soát Ranh giới Hành chính (Official vs OSM)</h1>
        <p>Hệ thống tự động chạy đối soát ranh giới cấp Xã/Phường Việt Nam</p>
        
        <h2>Tổng quan kết quả đối soát</h2>
        <div class="summary-cards">
            <div class="card">
                <div>Tổng số xã Nhà nước (Official)</div>
                <div class="card-value">{stats["Summary"]["total_official"]}</div>
            </div>
            <div class="card success">
                <div>Trùng khớp hoàn hảo (&ge;98% trùng)</div>
                <div class="card-value">{stats["Summary"]["perfect_match"]}</div>
            </div>
            <div class="card warning">
                <div>Vùng cần sửa ranh giới (Lệch ranh giới)</div>
                <div class="card-value">{stats["Summary"]["need_update"]}</div>
            </div>
            <div class="card danger">
                <div>Vùng cần thêm mới (Thiếu trên OSM)</div>
                <div class="card-value">{stats["Summary"]["need_add"]}</div>
            </div>
            <div class="card">
                <div>Vùng cần xóa ở OSM (Thừa trên OSM)</div>
                <div class="card-value">{stats["Summary"]["need_delete"]}</div>
            </div>
        </div>
 
        <h2>Biểu đồ phân tích</h2>
        <div class="charts">
            {"<div class='chart-container'><h3>Tỉ lệ trùng khớp hình học</h3><img src='data:image/png;base64," + hist_base64 + "' /></div>" if hist_base64 else ""}
            {"<div class='chart-container'><h3>Tỉ lệ phần trăm các nhóm</h3><img src='data:image/png;base64," + pie_base64 + "' /></div>" if pie_base64 else ""}
        </div>
 
        <h2>Top 100 Xã lệch ranh giới nhiều nhất (Theo diện tích lệch m²)</h2>
        <table>
            <thead>
                <tr>
                    <th>Mã Xã Official</th>
                    <th>Tên Xã Official</th>
                    <th>Tỉnh/Thành phố</th>
                    <th>OSM Relation ID</th>
                    <th>Tên Xã OSM</th>
                    <th>Tỷ lệ trùng</th>
                    <th>Chỉ số IoU</th>
                    <th>Diện tích lệch (m²)</th>
                    <th>Khoảng cách Hausdorff (m)</th>
                </tr>
            </thead>
            <tbody>
                {top_rows_html}
            </tbody>
        </table>
    </div>
</body>
</html>
"""
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        logger.info(f"Statistics generated and saved to {output_dir}")
        return stats

if __name__ == "__main__":
    import time
    
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    compare_res_path = os.path.join(root_dir, "output", "comparison", "compare_result.json")
    missing_path = os.path.join(root_dir, "output", "comparison", "missing.geojson")
    new_path = os.path.join(root_dir, "output", "comparison", "new.geojson")
    
    print("=" * 60)
    print("BENCHMARK: STATISTICS & VISUALS GENERATION")
    print("=" * 60)
    
    if os.path.exists(compare_res_path) and os.path.exists(missing_path) and os.path.exists(new_path):
        # Load comparison results
        print(f"Loading comparison results from: {compare_res_path}")
        with open(compare_res_path, "r", encoding="utf-8") as f:
            compare_results = json.load(f)
            
        # Load missing/new counts
        print("Loading missing & new counts...")
        with open(missing_path, "r", encoding="utf-8") as f:
            missing_count = len(json.load(f).get("features", []))
        with open(new_path, "r", encoding="utf-8") as f:
            new_count = len(json.load(f).get("features", []))
            
        # Run Stats Generator
        print("Generating statistics reports and visual charts...")
        start = time.time()
        stats_gen = StatisticsGenerator(compare_results, missing_count, new_count)
        out_dir = os.path.join(root_dir, "output", "statistics")
        stats = stats_gen.generate(out_dir)
        end = time.time()
        
        print(f"--> Statistics phase completed in: {end - start:.2f} seconds")
    else:
        print("Required comparison outputs not found. Please run compare.py first.")
        
    print("=" * 60)
