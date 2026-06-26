SELECT COUNT(*) FROM planet_osm_polygon;

SELECT osm_id, name, admin_level, boundary FROM planet_osm_polygon WHERE boundary='administrative' ORDER BY admin_level DESC;

SELECT boundary, COUNT(*)
FROM planet_osm_polygon
GROUP BY boundary;

SELECT admin_level, COUNT(*)
FROM planet_osm_polygon
WHERE boundary='administrative'
GROUP BY admin_level
ORDER BY admin_level;


SELECT COUNT(*) FROM planet_osm_rels;


SELECT COUNT(*) FROM planet_osm_ways;