import asyncio
import json
import logging
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime

import httpx
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

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, markup=True)]
)
logger = logging.getLogger("layer_discovery")
console = Console()
logging.getLogger("httpx").setLevel(logging.WARNING)


class LayerDiscovery:
    def __init__(self, probe_report_path: str, output_dir: str = "reports"):
        self.probe_report_path = probe_report_path
        self.base_url = "https://email.bando.com.vn/cgi-bin/qgis_mapserv.fcgi.exe"
        if not os.path.isabs(output_dir):
            output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), output_dir)
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.timeout = httpx.Timeout(30.0)
        self.layers_data = {}

    def load_probe_report(self) -> dict:
        if not os.path.exists(self.probe_report_path):
            logger.error(f"Probe report not found at {self.probe_report_path}")
            return {}
        with open(self.probe_report_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _safe_parse_xml(self, xml_text: str):
        try:
            xml_text = re.sub(r'\sxmlns="[^"]+"', '', xml_text, count=1)
            return ET.fromstring(xml_text)
        except Exception as e:
            logger.error(f"Failed to parse XML: {e}")
            return None

    async def _fetch(self, client: httpx.AsyncClient, params: dict, retries: int = 3) -> httpx.Response:
        for attempt in range(retries):
            try:
                response = await client.get(self.base_url, params=params, timeout=self.timeout)
                response.raise_for_status()
                return response
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                logger.warning(f"[yellow]Request failed (attempt {attempt + 1}/{retries}): {e}[/yellow]")
                if attempt == retries - 1:
                    return None
                await asyncio.sleep(2 ** attempt)
        return None

    def classify_layer(self, name: str, title: str, has_geometry: bool) -> str:
        name_lower = (name or "").lower()
        title_lower = (title or "").lower()
        combined = f"{name_lower} {title_lower}"

        # Nếu không có geometry và từ WMS -> thường là Raster hoặc Basemap
        if not has_geometry:
            # Có thể kiểm tra thêm tên
            if any(k in combined for k in ["basemap", "nen", "background"]):
                return "Base Map"
            return "Raster"

        if any(k in combined for k in ["diaphan", "hanhchinh", "rgvn", "bien_gioi", "biengioi", "boundary", "tinh", "xa", "huyen"]):
            return "Administrative / Boundary"
        
        if any(k in combined for k in ["duong", "road", "traffic", "giao_thong"]):
            return "Road"
            
        if any(k in combined for k in ["label", "text", "ten", "chu"]):
            return "Label"
            
        return "Vector (Unknown)"

    async def fetch_wms_layer_details(self, client: httpx.AsyncClient, map_path: str) -> dict:
        """Lấy thông tin BoundingBox, Scale từ WMS GetCapabilities."""
        params = {
            "MAP": map_path,
            "SERVICE": "WMS",
            "REQUEST": "GetCapabilities"
        }
        res = await self._fetch(client, params)
        details = {}
        if res and res.status_code == 200:
            root = self._safe_parse_xml(res.text)
            if root is not None:
                # Tìm đệ quy các Layer
                for layer_node in root.findall(".//Layer"):
                    name_node = layer_node.find("Name")
                    if name_node is not None and name_node.text:
                        name = name_node.text
                        
                        bbox = None
                        bbox_node = layer_node.find("EX_GeographicBoundingBox")
                        if bbox_node is not None:
                            try:
                                minx = bbox_node.find("westBoundLongitude").text
                                maxx = bbox_node.find("eastBoundLongitude").text
                                miny = bbox_node.find("southBoundLatitude").text
                                maxy = bbox_node.find("northBoundLatitude").text
                                bbox = [float(minx), float(miny), float(maxx), float(maxy)]
                            except:
                                pass
                        
                        if bbox is None:
                            bbox_node = layer_node.find("BoundingBox")
                            if bbox_node is not None:
                                try:
                                    bbox = [
                                        float(bbox_node.attrib.get("minx", 0)),
                                        float(bbox_node.attrib.get("miny", 0)),
                                        float(bbox_node.attrib.get("maxx", 0)),
                                        float(bbox_node.attrib.get("maxy", 0))
                                    ]
                                except:
                                    pass

                        min_scale = layer_node.find("MinScaleDenominator")
                        max_scale = layer_node.find("MaxScaleDenominator")
                        scale = {
                            "min": float(min_scale.text) if min_scale is not None else None,
                            "max": float(max_scale.text) if max_scale is not None else None
                        }
                        
                        details[name] = {
                            "bbox": bbox,
                            "scale": scale
                        }
        return details

    async def fetch_wfs_feature_count(self, client: httpx.AsyncClient, map_path: str, layer_name: str) -> int:
        params = {
            "MAP": map_path,
            "SERVICE": "WFS",
            "VERSION": "1.1.0",
            "REQUEST": "GetFeature",
            "TYPENAME": layer_name,
            "RESULTTYPE": "hits"
        }
        res = await self._fetch(client, params, retries=1)
        if res and res.status_code == 200:
            root = self._safe_parse_xml(res.text)
            if root is not None:
                count = root.attrib.get("numberOfFeatures") or root.attrib.get("numberMatched")
                if count and count.isdigit():
                    return int(count)
        return None

    async def fetch_wfs_geometry_type(self, client: httpx.AsyncClient, map_path: str, layer_name: str) -> str:
        params = {
            "MAP": map_path,
            "SERVICE": "WFS",
            "VERSION": "1.1.0",
            "REQUEST": "DescribeFeatureType",
            "TYPENAME": layer_name
        }
        res = await self._fetch(client, params, retries=1)
        if res and res.status_code == 200:
            root = self._safe_parse_xml(res.text)
            if root is not None:
                # Find geometry column type
                for elem in root.findall(".//{http://www.w3.org/2001/XMLSchema}element"):
                    t = elem.attrib.get("type", "")
                    if "gml:" in t or "Geometry" in t or any(x in t for x in ["Point", "Line", "Polygon"]):
                        return t.split(":")[-1]
        return None

    async def analyze_map(self, client: httpx.AsyncClient, map_path: str, map_data: dict, progress, task_id):
        wms_layers = map_data.get("WMS", {}).get("layers", [])
        wfs_supported = map_data.get("WFS", {}).get("supported", False)
        
        # 1. Fetch WMS details for all layers in one go
        wms_details = await self.fetch_wms_layer_details(client, map_path)
        
        analyzed_layers = []
        for layer in wms_layers:
            name = layer.get("name")
            title = layer.get("title")
            
            layer_info = {
                "name": name,
                "title": title,
                "styles": layer.get("styles", []),
                "bbox": None,
                "scale": {"min": None, "max": None},
                "geometry_type": None,
                "feature_count": None,
                "classification": "Unknown"
            }
            
            # WMS bboxes and scales
            if name in wms_details:
                layer_info["bbox"] = wms_details[name]["bbox"]
                layer_info["scale"] = wms_details[name]["scale"]
            
            # WFS geometry and count (only if WFS is supported)
            has_geometry = False
            if wfs_supported:
                geom = await self.fetch_wfs_geometry_type(client, map_path, name)
                if geom:
                    layer_info["geometry_type"] = geom
                    has_geometry = True
                    
                count = await self.fetch_wfs_feature_count(client, map_path, name)
                if count is not None:
                    layer_info["feature_count"] = count
            
            # Classification
            layer_info["classification"] = self.classify_layer(name, title, has_geometry)
            
            analyzed_layers.append(layer_info)
            progress.advance(task_id)
            
        self.layers_data[map_path] = {
            "crs": map_data.get("WMS", {}).get("crs", []),
            "layers": analyzed_layers
        }

    async def run(self):
        report_data = self.load_probe_report()
        if not report_data:
            return
            
        logger.info("[bold green]Bắt đầu phân tích các Layer...[/bold green]")
        
        async with httpx.AsyncClient(verify=False) as client:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                
                total_layers = sum(len(d.get("WMS", {}).get("layers", [])) for d in report_data.values())
                main_task = progress.add_task("[cyan]Đang quét...", total=total_layers)
                
                for map_path, map_data in report_data.items():
                    await self.analyze_map(client, map_path, map_data, progress, main_task)

        self.generate_reports()

    def generate_reports(self):
        json_path = os.path.join(self.output_dir, "layers.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(self.layers_data, f, ensure_ascii=False, indent=4)
            
        md_path = os.path.join(self.output_dir, "layers.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("# Báo cáo Phân tích Layer\n\n")
            f.write(f"**Thời gian phân tích:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            for map_path, data in self.layers_data.items():
                f.write(f"## Project: `{map_path}`\n\n")
                
                # Nhóm layers theo classification
                grouped = {}
                for layer in data["layers"]:
                    cls = layer["classification"]
                    if cls not in grouped:
                        grouped[cls] = []
                    grouped[cls].append(layer)
                    
                for cls, layers in grouped.items():
                    f.write(f"### Nhóm: {cls} ({len(layers)} layers)\n")
                    f.write("| Tên | Tiêu đề | Geometry | Feature Count | Bounding Box |\n")
                    f.write("|---|---|---|---|---|\n")
                    for l in layers:
                        geom = l.get("geometry_type") or "N/A"
                        count = l.get("feature_count")
                        count_str = str(count) if count is not None else "N/A"
                        bbox = l.get("bbox")
                        bbox_str = f"[{bbox[0]:.2f}, {bbox[1]:.2f}, {bbox[2]:.2f}, {bbox[3]:.2f}]" if bbox else "N/A"
                        
                        f.write(f"| {l['name']} | {l['title']} | {geom} | {count_str} | {bbox_str} |\n")
                    f.write("\n")
                f.write("---\n\n")
                
        logger.info(f"[bold green]Đã sinh báo cáo phân tích tại: {self.output_dir}[/bold green]")

if __name__ == "__main__":
    import sys
    # Hỗ trợ tự động chạy với config từ root
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    probe_report = os.path.join(root_dir, "reports", "qgis_probe.json")
    
    discovery = LayerDiscovery(probe_report_path=probe_report)
    asyncio.run(discovery.run())
