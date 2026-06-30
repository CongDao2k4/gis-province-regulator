import os
import sys
import logging
import geopandas as gpd
from shapely.ops import unary_union

# Add project root to path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

from src.loader import GeoJSONLoader

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("tinh_loader")

class ProvinceLoader(GeoJSONLoader):
    """
    Subclass of GeoJSONLoader specialized for Province and National boundaries.
    Automatically generates a virtual Vietnam national boundary feature for Official dataset.
    """
    def load(self) -> gpd.GeoDataFrame:
        gdf = super().load()
        
        # If this is the official provinces dataset, append virtual Vietnam national boundary
        if self.name == "Official" and 'a02_tinh' in gdf.columns:
            logger.info("Generating virtual Vietnam national boundary by dissolving all provinces...")
            try:
                # Merge all province geometries
                vn_geom = unary_union(gdf['geometry'])
                
                import pandas as pd
                # Append Vietnam national boundary row
                vn_row = gpd.GeoDataFrame([{
                    'id': 'vietnam_national_border',
                    'a02_tinh': 'vietnam_national_border',
                    'a01_ten': 'Việt Nam',
                    'a03_gc': 'Biên giới Quốc gia Việt Nam',
                    'geometry': vn_geom
                }], crs=gdf.crs)
                
                gdf = pd.concat([gdf, vn_row], ignore_index=True)
                logger.info("Appended virtual Vietnam national boundary feature.")
            except Exception as e:
                logger.error(f"Failed to generate virtual Vietnam boundary: {e}")
                
        return gdf

if __name__ == "__main__":
    off_path = os.path.join(ROOT_DIR, "data", "official", "provinces.geojson")
    loader = ProvinceLoader(off_path, "Official")
    gdf = loader.load()
    print("Columns:", gdf.columns)
    print("Vietnam row exists:", any(gdf['a02_tinh'] == 'vietnam_national_border'))
