import { useEffect, useRef, useCallback } from 'react'
import Map from 'ol/Map'
import View from 'ol/View'
import TileLayer from 'ol/layer/Tile'
import OSM from 'ol/source/OSM'
import VectorLayer from 'ol/layer/Vector'
import VectorSource from 'ol/source/Vector'
import GeoJSON from 'ol/format/GeoJSON'
import { Style, Fill, Stroke } from 'ol/style'
import Overlay from 'ol/Overlay'
import 'ol/ol.css'
import { useMapContext } from '../context/MapContext'

export default function MapView() {
  const mapElement = useRef<HTMLDivElement>(null)
  const popupElement = useRef<HTMLDivElement>(null)
  const hoverOverlay = useRef<Overlay | null>(null)

  const {
    setMap, layerRefs, layers, opacities,
    selectedFeature, setSelectedFeature,
    highlightedId, showToast,
  } = useMapContext()

  // Track highlighted feature for styling
  const highlightedIdRef = useRef<string | null>(null)
  useEffect(() => { highlightedIdRef.current = highlightedId }, [highlightedId])

  useEffect(() => {
    if (!mapElement.current || !popupElement.current) return

    // ── Sources (lazy load via URL) ──
    const officialSource = new VectorSource({
      url: 'http://localhost:8000/official/communes',
      format: new GeoJSON(),
    })

    const osmBoundarySource = new VectorSource({
      url: 'http://localhost:8000/osm/communes',
      format: new GeoJSON(),
    })

    const diffSource = new VectorSource({
      url: 'http://localhost:8000/difference',
      format: new GeoJSON(),
    })

    const missingSource = new VectorSource({
      url: 'http://localhost:8000/missing',
      format: new GeoJSON(),
    })

    const newSource = new VectorSource({
      url: 'http://localhost:8000/new',
      format: new GeoJSON(),
    })

    // ── Styles ── (promptui06 colors)
    // Official = Cam (orange)
    const officialStyle = new Style({
      fill: new Fill({ color: 'rgba(249, 115, 22, 0.08)' }),
      stroke: new Stroke({ color: '#f97316', width: 1.5 }),
    })

    // OSM = Xanh (blue)
    const osmBoundaryStyle = new Style({
      fill: new Fill({ color: 'rgba(56, 189, 248, 0.08)' }),
      stroke: new Stroke({ color: '#38bdf8', width: 1.5 }),
    })

    // Difference style function
    const diffStyleFunc = (feature: any) => {
      const fid = feature.get('official_id') || feature.getId()
      const isHighlighted = highlightedIdRef.current && fid === highlightedIdRef.current

      const color = feature.get('fillColor') || 'red'
      let fillColor = 'rgba(239, 68, 68, 0.6)' // Changed = Đỏ
      let strokeColor = '#ef4444'

      if (color === 'red') {
        fillColor = 'rgba(239, 68, 68, 0.6)'
        strokeColor = '#ef4444'
      } else if (color === 'blue') {
        fillColor = 'rgba(56, 189, 248, 0.6)'
        strokeColor = '#38bdf8'
      } else if (color === 'yellow') {
        fillColor = 'rgba(234, 179, 8, 0.4)' // New = Vàng
        strokeColor = '#eab308'
      } else if (color === 'purple') {
        fillColor = 'rgba(168, 85, 247, 0.6)' // Missing = Tím
        strokeColor = '#a855f7'
      } else if (color === 'green') {
        fillColor = 'rgba(74, 222, 128, 0.3)' // Matched = Xanh lá
        strokeColor = '#4ade80'
      }

      return new Style({
        fill: new Fill({ color: isHighlighted ? 'rgba(255, 255, 255, 0.35)' : fillColor }),
        stroke: new Stroke({
          color: isHighlighted ? '#ffffff' : strokeColor,
          width: isHighlighted ? 3 : 2,
        }),
      })
    }

    // Missing = Tím
    const missingStyle = new Style({
      fill: new Fill({ color: 'rgba(168, 85, 247, 0.2)' }),
      stroke: new Stroke({ color: '#a855f7', width: 2, lineDash: [4, 4] }),
    })

    // New = Vàng
    const newStyle = new Style({
      fill: new Fill({ color: 'rgba(234, 179, 8, 0.2)' }),
      stroke: new Stroke({ color: '#eab308', width: 2, lineDash: [4, 4] }),
    })

    // ── Layers ──
    const osmBaseLayer = new TileLayer({
      source: new OSM(),
      visible: layers.osmBase,
      opacity: opacities.osmBase,
    })

    const officialLayer = new VectorLayer({
      source: officialSource,
      style: officialStyle,
      visible: layers.official,
      opacity: opacities.official,
    })

    const osmBoundaryLayer = new VectorLayer({
      source: osmBoundarySource,
      style: osmBoundaryStyle,
      visible: layers.osmBoundary,
      opacity: opacities.osmBoundary,
    })

    const diffLayer = new VectorLayer({
      source: diffSource,
      style: diffStyleFunc,
      visible: layers.difference,
      opacity: opacities.difference,
    })

    const missingLayer = new VectorLayer({
      source: missingSource,
      style: missingStyle,
      visible: layers.missing,
      opacity: opacities.missing,
    })

    const newLayer = new VectorLayer({
      source: newSource,
      style: newStyle,
      visible: layers.newBoundary,
      opacity: opacities.newBoundary,
    })

    // Store refs
    layerRefs.current = {
      osmBase: osmBaseLayer,
      official: officialLayer,
      osmBoundary: osmBoundaryLayer,
      difference: diffLayer,
      missing: missingLayer,
      newBoundary: newLayer,
    }

    // ── Popup Overlay ──
    const popup = new Overlay({
      element: popupElement.current,
      positioning: 'bottom-center',
      stopEvent: true,
      offset: [0, -10],
    })

    // Fit to diff layer when loaded
    diffSource.on('featuresloadend', () => {
      const extent = diffSource.getExtent()
      if (extent && extent[0] !== Infinity && extent[0] !== -Infinity) {
        map.getView().fit(extent, { padding: [50, 50, 50, 50], maxZoom: 14 })
      }
    })

    // ── Map Init ──
    const map = new Map({
      target: mapElement.current,
      layers: [osmBaseLayer, officialLayer, osmBoundaryLayer, diffLayer, missingLayer, newLayer],
      overlays: [popup],
      view: new View({
        center: [11796120.31, 1797825.13],
        zoom: 6,
      }),
    })

    // ── Click handler ──
    map.on('click', (evt) => {
      const feature = map.forEachFeatureAtPixel(evt.pixel, (feat) => feat)
      if (feature) {
        const props = feature.getProperties()
        delete props.geometry // don't store geometry in state
        setSelectedFeature(props)
        popup.setPosition(evt.coordinate)
      } else {
        setSelectedFeature(null)
        popup.setPosition(undefined)
      }
    })

    // ── Hover handler (promptui14) ──
    let lastHoveredFeature: any = null
    map.on('pointermove', (e) => {
      const hit = map.hasFeatureAtPixel(e.pixel)
      map.getTargetElement().style.cursor = hit ? 'pointer' : ''

      // Hover highlight
      const feature = map.forEachFeatureAtPixel(e.pixel, (feat) => feat)
      if (feature !== lastHoveredFeature) {
        if (lastHoveredFeature) {
          lastHoveredFeature.changed() // trigger re-render with normal style
        }
        lastHoveredFeature = feature || null
        if (feature) {
          feature.changed()
        }
      }
    })

    setMap(map)

    return () => {
      map.setTarget(undefined)
      setMap(null)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <div className="map-container" ref={mapElement} />
      <div className="ol-popup" ref={popupElement}>
        {selectedFeature && <FeaturePopupContent feature={selectedFeature} />}
      </div>
    </>
  )
}

// ── Inline Popup Content (promptui03) ──
function FeaturePopupContent({ feature }: { feature: any }) {
  const { showToast, map } = useMapContext()

  const handleZoom = useCallback(() => {
    // Already zoomed on click, but re-fit
    if (map) {
      const overlays = map.getOverlays().getArray()
      if (overlays[0]) {
        const pos = overlays[0].getPosition()
        if (pos) {
          map.getView().animate({ center: pos, zoom: 14, duration: 600 })
        }
      }
    }
  }, [map])

  const handleCopyName = useCallback(() => {
    const name = feature.a03_ten || feature.official_name || feature.osm_name || feature.name || ''
    navigator.clipboard.writeText(name).then(() => {
      showToast('Đã copy tên: ' + name, 'success')
    })
  }, [feature, showToast])

  const handleExportGeoJSON = useCallback(() => {
    const data = JSON.stringify({ type: 'Feature', properties: feature, geometry: null }, null, 2)
    const blob = new Blob([data], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${feature.a03_ten || feature.name || 'feature'}.geojson`
    a.click()
    URL.revokeObjectURL(url)
    showToast('Exported GeoJSON', 'success')
  }, [feature, showToast])

  const isDiff = !!feature.fillColor || !!feature.overlap_ratio
  const isMissing = feature.category === 'Missing in OSM'
  const isNew = feature.category === 'New in OSM'

  return (
    <div className="popup-content">
      <h4>Feature Details</h4>

      {/* OSM Section */}
      {(isDiff || isNew) && (
        <div className="popup-section">
          <div className="popup-section-header osm-header">OSM</div>
          <p><strong>Tên:</strong> {feature.osm_name || feature.name || 'N/A'}</p>
          {feature.osm_id && <p><strong>OSM ID:</strong> {feature.osm_id}</p>}
          {feature.area_osm_sqm && <p><strong>Area:</strong> {(feature.area_osm_sqm / 1e6).toFixed(2)} km²</p>}
        </div>
      )}

      {/* Official Section */}
      {(isDiff || isMissing) && (
        <div className="popup-section">
          <div className="popup-section-header official-header">Official</div>
          <p><strong>Tên:</strong> {feature.a03_ten || feature.official_name || 'N/A'}</p>
          {feature.official_id && <p><strong>ID:</strong> {feature.official_id}</p>}
          {feature.a04_tentinh && <p><strong>Tỉnh:</strong> {feature.a04_tentinh}</p>}
          {feature.province && <p><strong>Tỉnh:</strong> {feature.province}</p>}
          {feature.area_official_sqm && <p><strong>Diện tích:</strong> {(feature.area_official_sqm / 1e6).toFixed(2)} km²</p>}
        </div>
      )}

      {/* Compare Section */}
      {isDiff && (
        <div className="popup-section">
          <div className="popup-section-header compare-header">Compare</div>
          <p><strong>Overlap:</strong> {feature.overlap_ratio ? `${(feature.overlap_ratio * 100).toFixed(1)}%` : 'N/A'}</p>
          <p><strong>IoU:</strong> {feature.iou ? `${(feature.iou * 100).toFixed(1)}%` : 'N/A'}</p>
          <p><strong>Hausdorff:</strong> {feature.hausdorff ? `${feature.hausdorff.toFixed(0)}m` : 'N/A'}</p>
          <p><strong>Area Diff:</strong> {feature.area_difference_sqm ? `${(feature.area_difference_sqm / 1e6).toFixed(3)} km²` : 'N/A'}</p>
          {feature.category && (
            <p><strong>Status:</strong> <span className={`cat-pill ${feature.fillColor === 'green' ? 'green-pill' : feature.fillColor === 'red' ? 'red-pill' : 'blue-pill'}`}>{feature.category}</span></p>
          )}
        </div>
      )}

      {/* Fallback for Official/OSM layer clicks (no compare data) */}
      {!isDiff && !isMissing && !isNew && (
        <div className="popup-section">
          <p><strong>Tên:</strong> {feature.name || feature.a03_ten || 'N/A'}</p>
          <p><strong>ID:</strong> {feature.id || feature.a02_xa || 'N/A'}</p>
          {feature.a04_tentinh && <p><strong>Tỉnh:</strong> {feature.a04_tentinh}</p>}
        </div>
      )}

      {/* Missing category */}
      {isMissing && !isDiff && (
        <div className="popup-section">
          <div className="popup-section-header missing-header">Status</div>
          <p><span className="cat-pill purple-pill">Missing in OSM</span></p>
        </div>
      )}

      {/* New category */}
      {isNew && !isDiff && (
        <div className="popup-section">
          <div className="popup-section-header new-header">Status</div>
          <p><span className="cat-pill yellow-pill">New in OSM</span></p>
        </div>
      )}

      <hr />
      <div className="popup-actions">
        <strong>Actions</strong>
        <div className="action-row">
          <button className="action-btn" onClick={handleZoom} title="Zoom to feature">🔍 Zoom</button>
          <button className="action-btn" onClick={handleExportGeoJSON} title="Export as GeoJSON">📥 Export</button>
          <button className="action-btn primary" onClick={handleCopyName} title="Copy name">📋 Copy</button>
        </div>
      </div>
    </div>
  )
}
