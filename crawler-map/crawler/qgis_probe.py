import asyncio
import json
import logging
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime

import httpx

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

from rich.console import Console
from rich.logging import RichHandler
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

# Cấu hình logging với Rich
logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, markup=True)]
)
logger = logging.getLogger("qgis_probe")
console = Console()

# Tắt bớt log của httpx
logging.getLogger("httpx").setLevel(logging.WARNING)

class QGISProbe:
    def __init__(self, base_url: str, maps: list, output_dir: str = "reports"):
        self.base_url = base_url
        self.maps = maps
        self.output_dir = output_dir
        # Tìm lại folder reports ở root thay vì ở cwd nếu chạy từ thư mục con
        if not os.path.isabs(self.output_dir):
            # assume root is where gis-crawler is
            self.output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), self.output_dir)
            
        os.makedirs(self.output_dir, exist_ok=True)
        self.timeout = httpx.Timeout(30.0)
        self.results = {}

    async def _fetch(self, client: httpx.AsyncClient, params: dict, retries: int = 3) -> httpx.Response:
        """Thực hiện HTTP GET request với cơ chế retry."""
        for attempt in range(retries):
            try:
                response = await client.get(self.base_url, params=params, timeout=self.timeout)
                response.raise_for_status()
                return response
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                logger.warning(f"[yellow]Request failed (attempt {attempt + 1}/{retries}): {e}[/yellow]")
                if attempt == retries - 1:
                    logger.error(f"[red]All retries failed for {params}[/red]")
                    return None
                await asyncio.sleep(2 ** attempt)
        return None

    def _safe_parse_xml(self, xml_text: str):
        try:
            # Loại bỏ default namespace để dễ query nếu dùng cách thủ công, 
            # tuy nhiên dùng defusedxml hoặc xpath với {*} là tốt nhất.
            # Ở đây không dùng defusedxml vì không rõ có cài chưa, dùng builtin.
            # Thay the xmlns de parse de hon
            import re
            xml_text = re.sub(r'\sxmlns="[^"]+"', '', xml_text, count=1)
            root = ET.fromstring(xml_text)
            return root
        except Exception as e:
            logger.error(f"Failed to parse XML: {e}")
            return None

    async def check_wms(self, client: httpx.AsyncClient, map_path: str) -> dict:
        params = {
            "MAP": map_path,
            "SERVICE": "WMS",
            "REQUEST": "GetCapabilities"
        }
        res = await self._fetch(client, params)
        info = {"supported": False, "layers": [], "crs": [], "styles": [], "geometry_types": []}
        
        if res and res.status_code == 200:
            if "ServiceException" in res.text:
                return info
            info["supported"] = True
            root = self._safe_parse_xml(res.text)
            if root is not None:
                # Trích xuất CRS
                for crs_node in root.findall(".//CRS") + root.findall(".//SRS"):
                    if crs_node.text:
                        info["crs"].append(crs_node.text)
                info["crs"] = list(set(info["crs"]))

                # Trích xuất Layer
                for layer_node in root.findall(".//Layer/Layer"):
                    name_node = layer_node.find("Name")
                    title_node = layer_node.find("Title")
                    if name_node is not None:
                        name = name_node.text
                        title = title_node.text if title_node is not None else ""
                        
                        # Style
                        styles = []
                        for style_node in layer_node.findall("Style"):
                            style_name = style_node.find("Name")
                            if style_name is not None:
                                styles.append(style_name.text)
                        
                        info["layers"].append({
                            "name": name,
                            "title": title,
                            "styles": styles
                        })
                        info["styles"].extend(styles)
                
                info["styles"] = list(set(info["styles"]))
        return info

    async def check_wfs(self, client: httpx.AsyncClient, map_path: str) -> dict:
        params = {
            "MAP": map_path,
            "SERVICE": "WFS",
            "REQUEST": "GetCapabilities"
        }
        res = await self._fetch(client, params)
        info = {"supported": False, "formats": []}
        
        if res and res.status_code == 200:
             if "ServiceException" in res.text or "ExceptionReport" in res.text:
                 return info
             info["supported"] = True
             root = self._safe_parse_xml(res.text)
             if root is not None:
                 # Tìm output formats support cho GetFeature
                 for op_node in root.findall(".//Operation[@name='GetFeature']"):
                     for format_node in op_node.findall(".//Format"):
                         if format_node.text:
                             info["formats"].append(format_node.text)
        return info

    async def check_wmts(self, client: httpx.AsyncClient, map_path: str) -> dict:
        params = {
            "MAP": map_path,
            "SERVICE": "WMTS",
            "REQUEST": "GetCapabilities"
        }
        res = await self._fetch(client, params)
        info = {"supported": False}
        if res and res.status_code == 200 and "ServiceException" not in res.text and "ExceptionReport" not in res.text:
             info["supported"] = True
        return info

    async def test_get_feature_info(self, client: httpx.AsyncClient, map_path: str, layers: list) -> bool:
        if not layers: return False
        test_layer = layers[0]["name"]
        params = {
            "MAP": map_path,
            "SERVICE": "WMS",
            "VERSION": "1.3.0",
            "REQUEST": "GetFeatureInfo",
            "LAYERS": test_layer,
            "QUERY_LAYERS": test_layer,
            "CRS": "EPSG:4326",
            "BBOX": "-180,-90,180,90",
            "WIDTH": "256",
            "HEIGHT": "256",
            "I": "128",
            "J": "128",
            "INFO_FORMAT": "application/json"
        }
        res = await self._fetch(client, params)
        return res is not None and res.status_code == 200

    async def test_get_legend_graphic(self, client: httpx.AsyncClient, map_path: str, layers: list) -> bool:
        if not layers: return False
        test_layer = layers[0]["name"]
        params = {
            "MAP": map_path,
            "SERVICE": "WMS",
            "VERSION": "1.3.0",
            "REQUEST": "GetLegendGraphic",
            "LAYER": test_layer,
            "FORMAT": "image/png"
        }
        res = await self._fetch(client, params)
        return res is not None and res.status_code == 200 and "image/" in res.headers.get("content-type", "")

    async def test_describe_layer(self, client: httpx.AsyncClient, map_path: str, layers: list) -> bool:
        if not layers: return False
        test_layer = layers[0]["name"]
        params = {
            "MAP": map_path,
            "SERVICE": "WMS",
            "VERSION": "1.1.1",
            "REQUEST": "DescribeLayer",
            "LAYERS": test_layer
        }
        res = await self._fetch(client, params)
        return res is not None and res.status_code == 200

    async def test_describe_feature_type(self, client: httpx.AsyncClient, map_path: str, layers: list) -> bool:
        if not layers: return False
        test_layer = layers[0]["name"]
        params = {
            "MAP": map_path,
            "SERVICE": "WFS",
            "VERSION": "1.1.0",
            "REQUEST": "DescribeFeatureType",
            "TYPENAME": test_layer
        }
        res = await self._fetch(client, params)
        return res is not None and res.status_code == 200

    async def test_supported_formats(self, client: httpx.AsyncClient, map_path: str, layers: list) -> dict:
        formats = {"GeoJSON": False, "GML": False, "KML": False}
        if not layers: return formats
        test_layer = layers[0]["name"]
        
        tests = [
            ("GeoJSON", ["application/json", "GeoJSON", "application/vnd.geo+json"]),
            ("GML", ["GML3", "GML2", "text/xml; subtype=gml/3.1.1"]),
            ("KML", ["KML", "application/vnd.google-earth.kml+xml"])
        ]
        
        for format_name, format_values in tests:
            for fmt_val in format_values:
                params = {
                    "MAP": map_path,
                    "SERVICE": "WFS",
                    "VERSION": "1.1.0",
                    "REQUEST": "GetFeature",
                    "TYPENAME": test_layer,
                    "MAXFEATURES": "1",
                    "OUTPUTFORMAT": fmt_val
                }
                res = await self._fetch(client, params, retries=1)
                if res and res.status_code == 200 and "ExceptionReport" not in res.text:
                    formats[format_name] = True
                    break
        return formats

    async def run(self):
        logger.info("[bold green]Bắt đầu probe QGIS Server...[/bold green]")
        
        async with httpx.AsyncClient(verify=False) as client:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                
                main_task = progress.add_task("[cyan]Đang quét các project...", total=len(self.maps))
                
                for map_path in self.maps:
                    progress.update(main_task, description=f"[cyan]Đang xử lý: {os.path.basename(map_path)}")
                    
                    self.results[map_path] = {}
                    
                    # 1. WMS
                    wms_info = await self.check_wms(client, map_path)
                    self.results[map_path]["WMS"] = wms_info
                    
                    # 2. WFS
                    wfs_info = await self.check_wfs(client, map_path)
                    self.results[map_path]["WFS"] = wfs_info
                    
                    # 3. WMTS
                    wmts_info = await self.check_wmts(client, map_path)
                    self.results[map_path]["WMTS"] = wmts_info
                    
                    layers = wms_info.get("layers", [])
                    
                    # 4. GetFeatureInfo
                    gfi = await self.test_get_feature_info(client, map_path, layers)
                    self.results[map_path]["GetFeatureInfo"] = gfi
                    
                    # 5. GetLegendGraphic
                    glg = await self.test_get_legend_graphic(client, map_path, layers)
                    self.results[map_path]["GetLegendGraphic"] = glg
                    
                    # 6. DescribeLayer
                    dl = await self.test_describe_layer(client, map_path, layers)
                    self.results[map_path]["DescribeLayer"] = dl
                    
                    # 7. DescribeFeatureType
                    dft = await self.test_describe_feature_type(client, map_path, layers)
                    self.results[map_path]["DescribeFeatureType"] = dft
                    
                    # 8 & 9. Formats
                    formats = await self.test_supported_formats(client, map_path, layers)
                    self.results[map_path]["Formats"] = formats
                    
                    progress.advance(main_task)

        self.generate_reports()

    def generate_reports(self):
        # Xuất file JSON
        json_path = os.path.join(self.output_dir, "qgis_probe.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(self.results, f, ensure_ascii=False, indent=4)
            
        # Xuất file Markdown
        md_path = os.path.join(self.output_dir, "qgis_probe.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("# Báo cáo Audit QGIS Server\n\n")
            f.write(f"**Thời gian quét:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"**Target URL:** `{self.base_url}`\n\n")
            
            for map_path, data in self.results.items():
                f.write(f"## Project: `{map_path}`\n\n")
                
                # Trạng thái service
                wms_sup = "✅" if data.get("WMS", {}).get("supported") else "❌"
                wfs_sup = "✅" if data.get("WFS", {}).get("supported") else "❌"
                wmts_sup = "✅" if data.get("WMTS", {}).get("supported") else "❌"
                f.write("### Services\n")
                f.write(f"- WMS: {wms_sup}\n")
                f.write(f"- WFS: {wfs_sup}\n")
                f.write(f"- WMTS: {wmts_sup}\n\n")
                
                # Khả năng gọi API
                f.write("### API Capabilities\n")
                f.write(f"- GetFeatureInfo: {'✅' if data.get('GetFeatureInfo') else '❌'}\n")
                f.write(f"- GetLegendGraphic: {'✅' if data.get('GetLegendGraphic') else '❌'}\n")
                f.write(f"- DescribeLayer: {'✅' if data.get('DescribeLayer') else '❌'}\n")
                f.write(f"- DescribeFeatureType: {'✅' if data.get('DescribeFeatureType') else '❌'}\n\n")
                
                # Formats
                f.write("### Supported Download Formats (GetFeature)\n")
                formats = data.get("Formats", {})
                f.write(f"- GeoJSON: {'✅' if formats.get('GeoJSON') else '❌'}\n")
                f.write(f"- GML: {'✅' if formats.get('GML') else '❌'}\n")
                f.write(f"- KML: {'✅' if formats.get('KML') else '❌'}\n\n")
                
                # Layer Details
                layers = data.get("WMS", {}).get("layers", [])
                f.write(f"### Layers ({len(layers)})\n")
                if layers:
                    f.write("| Tên | Tiêu đề | Styles |\n")
                    f.write("|---|---|---|\n")
                    for l in layers[:50]: # Giới hạn in 50 layer cho đỡ dài báo cáo
                        style_str = ", ".join(l.get("styles", []))
                        f.write(f"| {l['name']} | {l['title']} | {style_str} |\n")
                    if len(layers) > 50:
                        f.write(f"| ... | ... ({len(layers) - 50} layers ẩn) | ... |\n")
                else:
                    f.write("Không tìm thấy layer nào.\n")
                f.write("\n---\n\n")
                
        logger.info(f"[bold green]Đã sinh báo cáo thành công tại: {self.output_dir}[/bold green]")

if __name__ == "__main__":
    BASE_URL = "https://email.bando.com.vn/cgi-bin/qgis_mapserv.fcgi.exe"
    MAPS = [
        "d:/qgisserver/sapnhap/vnsapnhap10.qgz",
        "d:/qgisserver/sapnhap/rgvn8.qgz"
    ]
    
    probe = QGISProbe(base_url=BASE_URL, maps=MAPS)
    asyncio.run(probe.run())
