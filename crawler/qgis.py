import httpx
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')

class SapNhapCrawler:
    def __init__(self):
        self.wfs_url = "https://email.bando.com.vn/cgi-bin/qgis_mapserv.fcgi.exe"
        self.map_file = "D:/qgisserver/sapnhap/vnsapnhap10.qgz"
        self.output_dir = "data/raw_official"
        os.makedirs(self.output_dir, exist_ok=True)

    def fetch_layer(self, layer_name, output_file):
        print(f"[+] Đang tải dữ liệu thực tế từ WFS Layer: {layer_name}...")
        
        params = {
            "SERVICE": "WFS",
            "VERSION": "1.1.0",
            "REQUEST": "GetFeature",
            "TYPENAME": layer_name,
            "OUTPUTFORMAT": "application/json",
            "MAP": self.map_file
        }
        
        try:
            # Dùng httpx thay vì requests để tắt verify dễ hơn và nhanh hơn
            with httpx.Client(verify=False, timeout=60.0) as client:
                res = client.get(self.wfs_url, params=params)
                
                if res.status_code == 200:
                    data = res.json()
                    
                    features_count = len(data.get('features', []))
                    print(f"    -> Đã tải thành công {features_count} vùng (Polygons).")
                    
                    output_path = os.path.join(self.output_dir, output_file)
                    with open(output_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                        
                    print(f"    -> Đã lưu vào: {output_path}")
                    return True
                else:
                    print(f"[!] Lỗi WFS: HTTP {res.status_code}")
                    return False
        except Exception as e:
            print(f"[!] Lỗi kết nối: {e}")
            return False

    def run(self):
        print("="*60)
        print("KHỞI ĐỘNG CRAWLER WFS - LẤY DỮ LIỆU ĐỊA GIỚI HÀNH CHÍNH")
        print("Nguồn: https://sapnhap.bando.com.vn/pread_json")
        print("="*60)
        
        # 1. Tải cấp Tỉnh / Thành phố
        self.fetch_layer("diaphanhanhchinhcaptinh_sn", "provinces.geojson")
        
        # 2. Tải cấp Xã / Phường
        self.fetch_layer("diaphanhanhchinhcapxa_2025", "boundary.geojson")
        
        print("\n[✓] Hoàn tất quá trình Crawl dữ liệu thực tế!")

if __name__ == "__main__":
    crawler = SapNhapCrawler()
    crawler.run()
