import os
import sys
import json
import logging
import base64
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Add project root to path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("tinh_stats")

class ProvinceStatisticsGenerator:
    """
    Generates statistics reports for Provinces/National boundaries comparison.
    """
    def __init__(self, compare_results: list, missing_count: int, new_count: int):
        self.df = pd.DataFrame(compare_results)
        self.missing_count = missing_count
        self.new_count = new_count
        
    def generate(self, output_dir: str):
        logger.info("Generating province statistics and reports...")
        os.makedirs(output_dir, exist_ok=True)
        
        stats = {}
        
        if not self.df.empty:
            perfect_matches = self.df[self.df['overlap_ratio'] >= 0.95]
            changed = self.df[self.df['overlap_ratio'] < 0.95]
            
            # Count name mismatches (similarity < 90%)
            name_mismatches = self.df[self.df['name_similarity'] < 0.90]
            name_mismatch_count = len(name_mismatches)
            
            stats["Summary"] = {
                "total_official": len(self.df) + self.missing_count,
                "total_matched": len(self.df),
                "perfect_match": len(perfect_matches),
                "need_update": len(changed),
                "need_add": self.missing_count,
                "need_delete": self.new_count,
                "name_mismatch": name_mismatch_count
            }
        else:
            stats["Summary"] = {
                "total_official": self.missing_count,
                "total_matched": 0,
                "perfect_match": 0,
                "need_update": 0,
                "need_add": self.missing_count,
                "need_delete": self.new_count,
                "name_mismatch": 0
            }
            
        # 1. Generate charts
        hist_base64 = ""
        pie_base64 = ""
        
        try:
            if not self.df.empty:
                # Histogram
                plt.figure(figsize=(6, 4))
                plt.hist(self.df['overlap_ratio'] * 100, bins=10, color='#9b59b6', edgecolor='black', alpha=0.7)
                plt.title("Biểu đồ phân phối tỉ lệ trùng khớp Tỉnh (%)", fontsize=12, fontweight='bold')
                plt.xlabel("Tỉ lệ trùng khớp (%)", fontsize=10)
                plt.ylabel("Tần suất", fontsize=10)
                plt.grid(axis='y', linestyle='--', alpha=0.7)
                plt.tight_layout()
                
                hist_path = os.path.join(output_dir, "overlap_histogram.png")
                plt.savefig(hist_path, dpi=150)
                plt.close()
                
                with open(hist_path, "rb") as image_file:
                    hist_base64 = base64.b64encode(image_file.read()).decode('utf-8')
                    
                # Pie Chart
                plt.figure(figsize=(6, 4))
                labels = ['Khớp hoàn hảo', 'Cần sửa', 'Thiếu ranh giới']
                sizes = [stats["Summary"]["perfect_match"], stats["Summary"]["need_update"], stats["Summary"]["need_add"]]
                colors = ['#2ecc71', '#f1c40f', '#e74c3c']
                
                # Filter out zero values
                filtered_labels = []
                filtered_sizes = []
                filtered_colors = []
                for l, s, c in zip(labels, sizes, colors):
                    if s > 0:
                        filtered_labels.append(l)
                        filtered_sizes.append(s)
                        filtered_colors.append(c)
                        
                if filtered_sizes:
                    plt.pie(filtered_sizes, labels=filtered_labels, colors=filtered_colors, autopct='%1.1f%%', startangle=140)
                    plt.title("Tỉ lệ phần trăm các nhóm ranh giới Tỉnh", fontsize=12, fontweight='bold')
                    plt.tight_layout()
                    
                    pie_path = os.path.join(output_dir, "status_pie_chart.png")
                    plt.savefig(pie_path, dpi=150)
                    plt.close()
                    
                    with open(pie_path, "rb") as image_file:
                        pie_base64 = base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            logger.error(f"Error generating province charts: {e}")
            
        # 2. Get Top differences
        if not self.df.empty:
            top_diff = self.df.sort_values(by="area_difference_sqm", ascending=False)
        else:
            top_diff = pd.DataFrame()
            
        # 3. Export data
        stats_json_path = os.path.join(output_dir, "statistics.json")
        with open(stats_json_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, ensure_ascii=False, indent=4)
            
        top_csv_path = os.path.join(output_dir, "statistics.csv")
        top_diff.to_csv(top_csv_path, index=False, encoding="utf-8")
        
        # 4. Generate HTML
        html_path = os.path.join(output_dir, "statistics.html")
        
        top_rows_html = ""
        if not top_diff.empty:
            for _, r in top_diff.iterrows():
                top_rows_html += f"""
                <tr>
                    <td>{r['official_id']}</td>
                    <td>{r['official_name']}</td>
                    <td>{r['osm_id']}</td>
                    <td>{r['osm_name']}</td>
                    <td>{r['overlap_ratio']*100:.2f}%</td>
                    <td>{r['iou']*100:.2f}%</td>
                    <td>{r['area_difference_sqm']:,.1f}</td>
                    <td>{r['hausdorff']:,.2f}</td>
                </tr>
                """
        else:
            top_rows_html = "<tr><td colspan='8' style='text-align:center;'>Không tìm thấy tỉnh nào có sai lệch.</td></tr>"
            
        name_rows_html = ""
        if not self.df.empty:
            name_mismatches_df = self.df[self.df['name_similarity'] < 0.90].sort_values(by="name_similarity")
            if not name_mismatches_df.empty:
                for _, r in name_mismatches_df.iterrows():
                    name_rows_html += f"""
                    <tr>
                        <td>{r['official_id']}</td>
                        <td>{r['official_name']}</td>
                        <td>{r['osm_id']}</td>
                        <td>{r['osm_name']}</td>
                        <td>{r['name_similarity']*100:.1f}%</td>
                        <td>{r['overlap_ratio']*100:.2f}%</td>
                    </tr>
                    """
        if not name_rows_html:
            name_rows_html = "<tr><td colspan='6' style='text-align:center; color:#7f8c8d;'>Không có tỉnh nào sai lệch tên gọi theo chuẩn NFC.</td></tr>"
            
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Báo cáo Thống kê Đối soát Ranh giới cấp Tỉnh & Biên giới Việt Nam</title>
    <style>
        body {{ font-family: 'Segoe UI', sans-serif; background-color: #f8f9fa; color: #333; padding: 20px; }}
        .container {{ max-width: 1200px; margin: 0 auto; background-color: #fff; padding: 30px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
        h1, h2 {{ color: #2c3e50; border-bottom: 2px solid #ecf0f1; padding-bottom: 10px; }}
        .summary-cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin-bottom: 30px; }}
        .card {{ background-color: #f1f2f6; padding: 15px; border-radius: 6px; text-align: center; border-left: 5px solid #9b59b6; }}
        .card.success {{ border-left-color: #2ecc71; }}
        .card.warning {{ border-left-color: #f1c40f; }}
        .card.danger {{ border-left-color: #e74c3c; }}
        .card-value {{ font-size: 28px; font-weight: bold; color: #2c3e50; margin-top: 5px; }}
        .charts {{ display: flex; flex-wrap: wrap; gap: 30px; justify-content: center; margin-bottom: 40px; }}
        .chart-container {{ background: #fff; border: 1px solid #e1e8ed; border-radius: 6px; padding: 10px; text-align: center; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; font-size: 14px; }}
        th, td {{ padding: 12px 15px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background-color: #2c3e50; color: white; }}
        tr:hover {{ background-color: #f5f6fa; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Báo cáo Thống kê Đối soát Ranh giới cấp Tỉnh & Biên giới Việt Nam</h1>
        
        <h2>Tổng quan kết quả đối soát</h2>
        <div class="summary-cards">
            <div class="card">
                <div>Tổng số đơn vị (Official)</div>
                <div class="card-value">{stats["Summary"]["total_official"]}</div>
            </div>
            <div class="card success">
                <div>Trùng khớp hoàn hảo (&ge;95% trùng)</div>
                <div class="card-value">{stats["Summary"]["perfect_match"]}</div>
            </div>
            <div class="card warning">
                <div>Vùng lệch ranh giới (&lt;95% trùng)</div>
                <div class="card-value">{stats["Summary"]["need_update"]}</div>
            </div>
            <div class="card warning" style="border-left-color: #8e44ad;">
                <div>Sai lệch tên gọi (NFC &lt;90%)</div>
                <div class="card-value">{stats["Summary"]["name_mismatch"]}</div>
            </div>
            <div class="card danger">
                <div>Thiếu trên OSM</div>
                <div class="card-value">{stats["Summary"]["need_add"]}</div>
            </div>
            <div class="card">
                <div>Thừa trên OSM</div>
                <div class="card-value">{stats["Summary"]["need_delete"]}</div>
            </div>
        </div>

        <h2>Biểu đồ phân tích</h2>
        <div class="charts">
            {"<div class='chart-container'><h3>Tỉ lệ trùng khớp hình học</h3><img src='data:image/png;base64," + hist_base64 + "' /></div>" if hist_base64 else ""}
            {"<div class='chart-container'><h3>Phân phối các nhóm</h3><img src='data:image/png;base64," + pie_base64 + "' /></div>" if pie_base64 else ""}
        </div>

        <h2>Chi tiết sai lệch ranh giới các Tỉnh</h2>
        <table>
            <thead>
                <tr>
                    <th>Mã Tỉnh Official</th>
                    <th>Tên Tỉnh Official</th>
                    <th>OSM Relation ID</th>
                    <th>Tên Tỉnh OSM</th>
                    <th>Tỷ lệ trùng</th>
                    <th>IoU</th>
                    <th>Diện tích lệch (m²)</th>
                    <th>Khoảng cách Hausdorff (m)</th>
                </tr>
            </thead>
            <tbody>
                {top_rows_html}
            </tbody>
        </table>

        <h2>Danh sách Tỉnh sai lệch tên gọi theo chuẩn NFC (Fuzzy Match &lt; 90%)</h2>
        <table>
            <thead>
                <tr>
                    <th>Mã Tỉnh Official</th>
                    <th>Tên Tỉnh Official</th>
                    <th>OSM Relation ID</th>
                    <th>Tên Tỉnh OSM</th>
                    <th>Độ tương đồng tên</th>
                    <th>Tỷ lệ trùng khớp ranh giới</th>
                </tr>
            </thead>
            <tbody>
                {name_rows_html}
            </tbody>
        </table>
    </div>
</body>
</html>
"""
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
            
        logger.info(f"Province statistics generated and saved to {output_dir}")
        return stats
