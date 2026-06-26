#!/bin/bash
set -e

mkdir -p data_osm

echo "[INFO] Downloading Vietnam OSM PBF..."

wget -c -O data_osm/vietnam-260601.osm.pbf \
  https://download.geofabrik.de/asia/vietnam-260601.osm.pbf
echo "[INFO] Download completed."
ls -lh data_osm/vietnam-260601.osm.pbf

#echo "[INFO] Basic file info:"
#file data_osm/vietnam-180101.osm.pbf
#
#echo "[INFO] Osmium file info:"
#osmium fileinfo data_osm/vietnam-180101.osm.pbf
