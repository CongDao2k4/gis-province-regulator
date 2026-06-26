import os
import sys
import logging
import geopandas as gpd

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("loader")

class GeoJSONLoader:
    """
    GeoJSON Loader module.
    Responsible for:
    - Loading GeoJSON boundary files.
    - Checking and converting CRS to EPSG:4326.
    - Validating geometries.
    - Fixing invalid geometries using make_valid().
    - Ensuring encoding is normalized.
    - Generating/exposing spatial index (sindex).
    """
    def __init__(self, file_path: str, name: str = "Dataset"):
        self.file_path = file_path
        self.name = name
        self.gdf = None

    def load(self) -> gpd.GeoDataFrame:
        logger.info(f"Loading {self.name} from: {self.file_path}")
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"File not found: {self.file_path}")

        # Load GeoJSON file
        try:
            # geopandas read_file uses utf-8 by default, but we enforce it
            self.gdf = gpd.read_file(self.file_path, encoding="utf-8")
            logger.info(f"Loaded {self.name}: {len(self.gdf)} features.")
        except Exception as e:
            logger.error(f"Error loading {self.name}: {e}")
            raise

        # Check and convert CRS to EPSG:4326 (WGS 84)
        if self.gdf.crs is None:
            logger.warning(f"{self.name} has no CRS defined. Setting to EPSG:4326.")
            self.gdf.set_crs(epsg=4326, inplace=True)
        elif self.gdf.crs.to_epsg() != 4326:
            logger.info(f"Reprojecting {self.name} from EPSG:{self.gdf.crs.to_epsg()} to EPSG:4326.")
            self.gdf = self.gdf.to_crs(epsg=4326)
        else:
            logger.info(f"{self.name} CRS is EPSG:4326.")

        # Check and fix geometry
        logger.info(f"Checking geometries for {self.name}...")
        invalid_mask = ~self.gdf.is_valid
        invalid_count = invalid_mask.sum()
        if invalid_count > 0:
            logger.warning(f"Found {invalid_count} invalid geometries in {self.name}. Applying make_valid()...")
            self.gdf['geometry'] = self.gdf['geometry'].make_valid()
            # Double check if any are still invalid
            still_invalid = (~self.gdf.is_valid).sum()
            if still_invalid > 0:
                logger.error(f"Failed to fix {still_invalid} geometries in {self.name}.")
            else:
                logger.info(f"All geometries in {self.name} are now valid.")
        else:
            logger.info(f"All geometries in {self.name} are valid.")

        # Drop rows with null geometry
        null_geom_count = self.gdf['geometry'].isna().sum()
        if null_geom_count > 0:
            logger.warning(f"Found {null_geom_count} features with null geometry in {self.name}. Removing them.")
            self.gdf = self.gdf.dropna(subset=['geometry'])

        # Trigger spatial index creation explicitly to cache it
        _ = self.gdf.sindex
        logger.info(f"{self.name} spatial index generated successfully.")

        return self.gdf

if __name__ == "__main__":
    import time
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    osm_path = os.path.join(root_dir, "data", "osm", "boundary.geojson")
    off_path = os.path.join(root_dir, "data", "official", "boundary.geojson")
    
    print("=" * 60)
    print("BENCHMARK: GEOJSON LOADING PHASE")
    print("=" * 60)
    
    # Benchmark OSM
    if os.path.exists(osm_path):
        start = time.time()
        loader = GeoJSONLoader(osm_path, "OSM")
        osm_gdf = loader.load()
        end = time.time()
        print(f"--> OSM dataset loaded in: {end - start:.2f} seconds")
    else:
        print(f"OSM file not found at: {osm_path}")
        
    # Benchmark Official
    if os.path.exists(off_path):
        start = time.time()
        loader = GeoJSONLoader(off_path, "Official")
        off_gdf = loader.load()
        end = time.time()
        print(f"--> Official dataset loaded in: {end - start:.2f} seconds")
    else:
        print(f"Official file not found at: {off_path}")
        
    print("=" * 60)
