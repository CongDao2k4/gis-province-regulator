import httpx
import asyncio
import json
import os
import csv
import sqlite3
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')

class DVHCCrawler:
    def __init__(self):
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.output_raw = os.path.join(root_dir, "data", "raw")
        self.output_csv = os.path.join(root_dir, "data", "csv")
        self.output_db = os.path.join(root_dir, "data", "dvhc.db")
        
        os.makedirs(self.output_raw, exist_ok=True)
        os.makedirs(self.output_csv, exist_ok=True)
        
        self.url = "https://sapnhap.bando.com.vn/p.co_dvhc"

    async def run(self):
        print("Đang cào dữ liệu hành chính (DVHC) từ server...")
        async with httpx.AsyncClient(verify=False) as client:
            res = await client.post(self.url, timeout=30.0)
            res.raise_for_status()
            data = res.json()
            
            # 1. Lưu JSON
            json_path = os.path.join(self.output_raw, "dvhc.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
            # 2. Lọc và đếm
            # Data format: [{"ma":"92","ten":"Thành Phố Cần Thơ","magoc":"0","malk":"diaphanhanhchinhcaptinh_sn.1","truocsapnhap":...}, ...]
            # Thường magoc="0" là Tỉnh/Thành phố. 
            # Dựa vào tên có thể biết là Tỉnh, Thành phố, Huyện, Xã.
            # Ta lưu tất cả vào CSV
            
            csv_path = os.path.join(self.output_csv, "dvhc.csv")
            if data:
                keys = data[0].keys()
                with open(csv_path, "w", encoding="utf-8", newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=keys)
                    writer.writeheader()
                    writer.writerows(data)
                    
            # 3. Lưu SQLite
            conn = sqlite3.connect(self.output_db)
            cursor = conn.cursor()
            cursor.execute("DROP TABLE IF EXISTS dvhc")
            columns = ", ".join([f"{k} TEXT" for k in keys])
            cursor.execute(f"CREATE TABLE dvhc ({columns})")
            
            placeholders = ", ".join(["?" for _ in keys])
            insert_sql = f"INSERT INTO dvhc VALUES ({placeholders})"
            for row in data:
                cursor.execute(insert_sql, list(row.values()))
            conn.commit()
            conn.close()
            
            # 4. Phân tích thống kê cơ bản
            tinh_tp = [d for d in data if "Tỉnh" in d.get("ten", "") or "Thành Phố" in d.get("ten", "")]
            xa_phuong = [d for d in data if d.get("ten", "").startswith("Xã ") or d.get("ten", "").startswith("Phường ") or d.get("ten", "").startswith("Thị trấn ")]
            
            print(f"Hoàn thành! Đã lưu {len(data)} bản ghi DVHC.")
            print(f"==> Số lượng Tỉnh/Thành phố: {len(tinh_tp)}")
            print(f"==> Số lượng Xã/Phường/Thị trấn: {len(xa_phuong)}")
            
            # Để chắc chắn, tính thử các loại
            loai_dict = {}
            for d in data:
                ten = d.get("ten", "")
                loai = ten.split(" ")[0] if ten else "Khác"
                loai_dict[loai] = loai_dict.get(loai, 0) + 1
            print("Chi tiết các loại tiền tố:")
            for k, v in loai_dict.items():
                print(f" - {k}: {v}")

if __name__ == "__main__":
    import asyncio
    crawler = DVHCCrawler()
    asyncio.run(crawler.run())
