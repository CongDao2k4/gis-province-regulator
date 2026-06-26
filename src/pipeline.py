import os
import sys
import logging
import json
from rich.console import Console

# Adjust python path to include this directory if run directly
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from loader import GeoJSONLoader
from matcher import BoundaryMatcher
from compare import GeometryComparer
from stats import StatisticsGenerator
from candidate import CandidateGenerator

# Set up logging with Rich
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("pipeline")
console = Console()

class Pipeline:
    def __init__(self, root_dir: str = None):
        if root_dir is None:
            self.root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        else:
            self.root_dir = root_dir
            
        self.osm_path = os.path.join(self.root_dir, "data", "osm", "boundary.geojson")
        self.official_path = os.path.join(self.root_dir, "data", "official", "boundary.geojson")
        
        # Segmented output subfolders
        self.output_dir = os.path.join(self.root_dir, "output")
        self.simplified_dir = os.path.join(self.output_dir, "simplified")
        self.comparison_dir = os.path.join(self.output_dir, "comparison")
        self.statistics_dir = os.path.join(self.output_dir, "statistics")
        self.candidates_dir = os.path.join(self.output_dir, "candidates")
        
        # Ensure all folders exist
        os.makedirs(self.simplified_dir, exist_ok=True)
        os.makedirs(self.comparison_dir, exist_ok=True)
        os.makedirs(self.statistics_dir, exist_ok=True)
        os.makedirs(self.candidates_dir, exist_ok=True)

    def run(self):
        console.print("[bold green]=========================================[/bold green]")
        console.print("[bold green]   STARTING GIS BOUNDARY MATCH PIPELINE   [/bold green]")
        console.print("[bold green]=========================================[/bold green]")

        # 1. Load Data
        console.print("\n[bold cyan]1. LOADING DATASETS[/bold cyan]")
        logger.info(f"OSM boundary path: {self.osm_path}")
        logger.info(f"Official boundary path: {self.official_path}")

        try:
            osm_loader = GeoJSONLoader(self.osm_path, "OSM")
            osm_gdf = osm_loader.load()
            
            off_loader = GeoJSONLoader(self.official_path, "Official")
            off_gdf = off_loader.load()
        except Exception as e:
            logger.critical(f"Data loading failed: {e}")
            sys.exit(1)

        # Simplify and save for WebGIS rendering to prevent browser crash
        console.print("\n[bold cyan]1.5. SIMPLIFYING BOUNDARIES FOR WEBGIS[/bold cyan]")
        logger.info("Simplifying geometries (tolerance=0.001) for fast WebGIS loading...")
        try:
            off_id_col = 'a02_xa' if 'a02_xa' in off_gdf.columns else ('id' if 'id' in off_gdf.columns else 'index')
            off_name_col = 'a03_ten' if 'a03_ten' in off_gdf.columns else 'name'
            off_prov_col = 'a04_tentinh' if 'a04_tentinh' in off_gdf.columns else 'province'
            
            osm_id_col = 'id' if 'id' in osm_gdf.columns else 'osm_id'
            osm_name_col = 'name' if 'name' in osm_gdf.columns else 'name'

            # Simplify Official
            off_simple = off_gdf.copy()
            off_simple['geometry'] = off_simple['geometry'].simplify(0.001, preserve_topology=True)
            cols_off = ['geometry']
            for col in [off_id_col, off_name_col, off_prov_col]:
                if col in off_simple.columns:
                    cols_off.append(col)
            off_simple = off_simple[cols_off]
            
            off_simple.to_file(os.path.join(self.simplified_dir, "official_communes.geojson"), driver="GeoJSON")
            logger.info("Exported simplified official communes.")

            # Simplify OSM
            osm_simple = osm_gdf.copy()
            osm_simple['geometry'] = osm_simple['geometry'].simplify(0.001, preserve_topology=True)
            cols_osm = ['geometry']
            for col in [osm_id_col, osm_name_col]:
                if col in osm_simple.columns:
                    cols_osm.append(col)
            osm_simple = osm_simple[cols_osm]
            
            osm_simple.to_file(os.path.join(self.simplified_dir, "osm_communes.geojson"), driver="GeoJSON")
            logger.info("Exported simplified OSM communes.")
        except Exception as e:
            logger.error(f"Failed to simplify boundaries: {e}")

        # 2. Match boundaries
        console.print("\n[bold cyan]2. MATCHING BOUNDARIES (SPATIAL & SEMANTIC JOIN)[/bold cyan]")
        matcher = BoundaryMatcher(off_gdf, osm_gdf)
        matches = matcher.match()

        # 3. Geometry Comparison
        console.print("\n[bold cyan]3. COMPARING GEOMETRIES[/bold cyan]")
        comparer = GeometryComparer(off_gdf, osm_gdf, matches)
        compare_results = comparer.run_compare(self.comparison_dir)

        # 4. Generate Statistics
        console.print("\n[bold cyan]4. GENERATING STATISTICS & VISUALS[/bold cyan]")
        # Read missing.geojson and new.geojson counts to pass to statistics generator
        try:
            with open(os.path.join(self.comparison_dir, "missing.geojson"), "r", encoding="utf-8") as f:
                missing_data = json.load(f)
                missing_count = len(missing_data.get("features", []))
            
            with open(os.path.join(self.comparison_dir, "new.geojson"), "r", encoding="utf-8") as f:
                new_data = json.load(f)
                new_count = len(new_data.get("features", []))
        except Exception as e:
            logger.error(f"Error loading difference files for stats count: {e}")
            missing_count = 0
            new_count = 0

        stats_gen = StatisticsGenerator(compare_results, missing_count, new_count)
        stats = stats_gen.generate(self.statistics_dir)

        # 5. Generate Candidates
        console.print("\n[bold cyan]5. GENERATING CANDIDATES[/bold cyan]")
        # Load missing features
        missing_features = missing_data.get("features", []) if 'missing_data' in locals() else []
        candidate_gen = CandidateGenerator(compare_results, missing_features, off_gdf)
        candidates = candidate_gen.generate(self.candidates_dir)

        console.print("\n[bold green]=========================================[/bold green]")
        console.print("[bold green]     PIPELINE COMPLETED SUCCESSFULLY!    [/bold green]")
        console.print("[bold green]=========================================[/bold green]")
        
        # Output simple summary
        print(f"Summary metrics:")
        print(f" - Perfect Match: {stats['Summary']['PerfectMatch']}")
        print(f" - Changed:       {stats['Summary']['Changed']}")
        print(f" - Missing:       {stats['Summary']['MissingInOSM']}")
        print(f" - New:           {stats['Summary']['NewInOSM']}")
        print(f"All output files written to segmented subfolders under: {self.output_dir}")

if __name__ == "__main__":
    pipeline = Pipeline()
    pipeline.run()
