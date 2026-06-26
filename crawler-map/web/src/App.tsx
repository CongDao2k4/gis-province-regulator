import { useEffect, useRef, useState } from 'react'
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
import './App.css'

interface LayerState {
  osmBase: boolean;
  official: boolean;
  osmBoundary: boolean;
  difference: boolean;
  missing: boolean;
  newBoundary: boolean;
}

interface OpacityState {
  osmBase: number;
  official: number;
  osmBoundary: number;
  difference: number;
  missing: number;
  newBoundary: number;
}

function App() {
  const mapElement = useRef<HTMLDivElement>(null)
  const popupElement = useRef<HTMLDivElement>(null)
  const mapRef = useRef<Map | null>(null)
  
  const [stats, setStats] = useState<any>(null)
  const [selectedFeature, setSelectedFeature] = useState<any>(null)
  
  // Layer visibility state
  const [layers, setLayers] = useState<LayerState>({
    osmBase: true,
    official: true,
    osmBoundary: false,
    difference: true,
    missing: true,
    newBoundary: true,
  })

  // Layer opacity state
  const [opacities, setOpacities] = useState<OpacityState>({
    osmBase: 1.0,
    official: 0.6,
    osmBoundary: 0.6,
    difference: 0.8,
    missing: 0.8,
    newBoundary: 0.8,
  })

  // Layer references
  const layersRef = useRef<{ [key: string]: TileLayer<any> | VectorLayer<any> }>({})

  // Search state
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<any[]>([])

  useEffect(() => {
    // Fetch stats on load
    fetch('http://localhost:8000/statistics')
      .then(res => res.json())
      .then(data => setStats(data))
      .catch(err => console.error("Error fetching stats:", err))
  }, [])

  useEffect(() => {
    if (!mapElement.current || !popupElement.current) return;

    // --- 1. Sources ---
    const officialSource = new VectorSource({
      url: 'http://localhost:8000/official/communes',
      format: new GeoJSON()
    })

    const osmBoundarySource = new VectorSource({
      url: 'http://localhost:8000/osm/communes',
      format: new GeoJSON()
    })

    const diffSource = new VectorSource({
      url: 'http://localhost:8000/difference',
      format: new GeoJSON()
    })

    const missingSource = new VectorSource({
      url: 'http://localhost:8000/missing',
      format: new GeoJSON()
    })

    const newSource = new VectorSource({
      url: 'http://localhost:8000/new',
      format: new GeoJSON()
    })

    // --- 2. Styles ---
    const officialStyle = new Style({
      fill: new Fill({ color: 'rgba(49, 134, 204, 0.08)' }),
      stroke: new Stroke({ color: '#3186cc', width: 1.5 })
    })

    const osmBoundaryStyle = new Style({
      fill: new Fill({ color: 'rgba(46, 204, 113, 0.08)' }),
      stroke: new Stroke({ color: '#2ecc71', width: 1.5 })
    })

    const diffStyleFunc = (feature: any) => {
      const color = feature.get('fillColor') || 'red'
      let fillColor = 'rgba(255, 0, 0, 0.6)'
      let strokeColor = '#e74c3c'
      
      if (color === 'red') {
        fillColor = 'rgba(231, 76, 60, 0.6)'
        strokeColor = '#e74c3c'
      } else if (color === 'blue') {
        fillColor = 'rgba(52, 152, 219, 0.6)'
        strokeColor = '#3498db'
      } else if (color === 'yellow') {
        fillColor = 'rgba(241, 196, 15, 0.4)'
        strokeColor = '#f1c40f'
      } else if (color === 'purple') {
        fillColor = 'rgba(155, 89, 182, 0.6)'
        strokeColor = '#9b59b6'
      }
      
      return new Style({
        fill: new Fill({ color: fillColor }),
        stroke: new Stroke({ color: strokeColor, width: 2 })
      })
    }

    const missingStyle = new Style({
      fill: new Fill({ color: 'rgba(231, 76, 60, 0.2)' }),
      stroke: new Stroke({ color: '#e74c3c', width: 2, lineDash: [4, 4] })
    })

    const newStyle = new Style({
      fill: new Fill({ color: 'rgba(52, 152, 219, 0.2)' }),
      stroke: new Stroke({ color: '#3498db', width: 2, lineDash: [4, 4] })
    })

    // --- 3. Layers ---
    const osmBaseLayer = new TileLayer({
      source: new OSM(),
      visible: layers.osmBase,
      opacity: opacities.osmBase
    })

    const officialLayer = new VectorLayer({
      source: officialSource,
      style: officialStyle,
      visible: layers.official,
      opacity: opacities.official
    })

    const osmBoundaryLayer = new VectorLayer({
      source: osmBoundarySource,
      style: osmBoundaryStyle,
      visible: layers.osmBoundary,
      opacity: opacities.osmBoundary
    })

    const diffLayer = new VectorLayer({
      source: diffSource,
      style: diffStyleFunc,
      visible: layers.difference,
      opacity: opacities.difference
    })

    const missingLayer = new VectorLayer({
      source: missingSource,
      style: missingStyle,
      visible: layers.missing,
      opacity: opacities.missing
    })

    const newLayer = new VectorLayer({
      source: newSource,
      style: newStyle,
      visible: layers.newBoundary,
      opacity: opacities.newBoundary
    })

    // Store layer references
    layersRef.current = {
      osmBase: osmBaseLayer,
      official: officialLayer,
      osmBoundary: osmBoundaryLayer,
      difference: diffLayer,
      missing: missingLayer,
      newBoundary: newLayer
    }

    // --- 4. Popup Overlay ---
    const popup = new Overlay({
      element: popupElement.current,
      positioning: 'bottom-center',
      stopEvent: true,
      offset: [0, -10],
    })

    // Fit map to difference layer bounds once loaded
    diffSource.on('featuresloadend', () => {
      const extent = diffSource.getExtent();
      if (extent && extent[0] !== Infinity && extent[0] !== -Infinity) {
        map.getView().fit(extent, { padding: [50, 50, 50, 50], maxZoom: 14 });
      }
    });

    // --- 5. Map Init ---
    const map = new Map({
      target: mapElement.current,
      layers: [
        osmBaseLayer,
        officialLayer,
        osmBoundaryLayer,
        diffLayer,
        missingLayer,
        newLayer
      ],
      overlays: [popup],
      view: new View({
        center: [11796120.31, 1797825.13], // Vietnam coordinates in EPSG:3857
        zoom: 6
      })
    })

    // --- 6. Event Handlers ---
    map.on('click', (evt) => {
      const feature = map.forEachFeatureAtPixel(evt.pixel, (feat) => feat)
      if (feature) {
        const props = feature.getProperties()
        setSelectedFeature(props)
        popup.setPosition(evt.coordinate)
      } else {
        setSelectedFeature(null)
        popup.setPosition(undefined)
      }
    })

    map.on('pointermove', (e) => {
      const hit = map.hasFeatureAtPixel(e.pixel)
      map.getTargetElement().style.cursor = hit ? 'pointer' : ''
    })

    mapRef.current = map

    return () => {
      map.setTarget(undefined)
    }
  }, [])

  // Sync layer visibility
  useEffect(() => {
    Object.keys(layers).forEach(key => {
      const layer = layersRef.current[key];
      if (layer) {
        layer.setVisible(layers[key as keyof LayerState]);
      }
    });
  }, [layers])

  // Sync layer opacity
  useEffect(() => {
    Object.keys(opacities).forEach(key => {
      const layer = layersRef.current[key];
      if (layer) {
        layer.setOpacity(opacities[key as keyof OpacityState]);
      }
    });
  }, [opacities])

  // Handle Layer Toggle
  const toggleLayer = (layerName: keyof LayerState) => {
    setLayers(prev => ({
      ...prev,
      [layerName]: !prev[layerName]
    }))
  }

  // Handle Opacity Change
  const changeOpacity = (layerName: keyof OpacityState, value: number) => {
    setOpacities(prev => ({
      ...prev,
      [layerName]: value
    }))
  }

  // Handle Search Input & Fetch
  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value
    setSearchQuery(val)
    if (val.trim().length >= 2) {
      fetch(`http://localhost:8000/search?q=${encodeURIComponent(val)}`)
        .then(res => res.json())
        .then(data => setSearchResults(data.features || []))
        .catch(err => console.error("Search error:", err))
    } else {
      setSearchResults([])
    }
  }

  // Navigate & Zoom to Search Feature
  const selectSearchFeature = (feat: any) => {
    if (!mapRef.current) return;
    
    const format = new GeoJSON()
    const olFeature = format.readFeature(feat, {
      dataProjection: 'EPSG:4326',
      featureProjection: 'EPSG:3857'
    })
    
    const geometry = olFeature.getGeometry()
    if (geometry) {
      const extent = geometry.getExtent()
      mapRef.current.getView().fit(extent, {
        duration: 1000,
        padding: [100, 100, 100, 100],
        maxZoom: 14
      })
      setSelectedFeature(feat.properties)
      // Set popup position to center/centroid
      const flatCoords = geometry.getExtent();
      const center = [(flatCoords[0] + flatCoords[2]) / 2, (flatCoords[1] + flatCoords[3]) / 2];
      
      // Update popup overlay
      const popup = mapRef.current.getOverlays().getArray()[0];
      if (popup) {
        popup.setPosition(center);
      }
    }
    setSearchResults([])
  }

  return (
    <div className="app-container dark-theme">
      <div className="sidebar">
        <div className="logo-section">
          <h2>GIS REGULATOR</h2>
          <span className="subtitle font-outfit">Boundary Checker</span>
        </div>

        {/* Section 1: Search */}
        <div className="sidebar-section search-section">
          <h3>🔍 Search Communes</h3>
          <div className="search-box">
            <input
              type="text"
              placeholder="Type commune name..."
              value={searchQuery}
              onChange={handleSearchChange}
            />
            {searchResults.length > 0 && (
              <ul className="search-results">
                {searchResults.map((feat, i) => (
                  <li key={i} onClick={() => selectSearchFeature(feat)}>
                    {feat.properties.a03_ten || feat.properties.name} 
                    <span className="result-prov">({feat.properties.a04_tentinh || 'N/A'})</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* Section 2: Layer Control */}
        <div className="sidebar-section layer-control-section">
          <h3>🗺️ Layer Control</h3>
          <div className="layer-list">
            {[
              { id: 'osmBase', label: 'Base Map (OSM)', color: '#bbb' },
              { id: 'official', label: 'Official Boundary', color: '#3186cc' },
              { id: 'osmBoundary', label: 'OSM Boundary', color: '#2ecc71' },
              { id: 'difference', label: 'Difference Areas', color: '#f1c40f' },
              { id: 'missing', label: 'Missing in OSM', color: '#e74c3c' },
              { id: 'newBoundary', label: 'New in OSM', color: '#3498db' }
            ].map(l => (
              <div className="layer-item" key={l.id}>
                <div className="layer-toggle-row">
                  <label className="checkbox-container">
                    <input
                      type="checkbox"
                      checked={layers[l.id as keyof LayerState]}
                      onChange={() => toggleLayer(l.id as keyof LayerState)}
                    />
                    <span className="checkmark" style={{ borderColor: l.color }}></span>
                    <span className="layer-label">{l.label}</span>
                  </label>
                </div>
                <div className="opacity-slider-row">
                  <span className="opacity-text">Opacity: {Math.round(opacities[l.id as keyof OpacityState] * 100)}%</span>
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={opacities[l.id as keyof OpacityState]}
                    onChange={(e) => changeOpacity(l.id as keyof OpacityState, parseFloat(e.target.value))}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Section 3: Statistics */}
        <div className="sidebar-section stats-section">
          <h3>📊 Statistics Summary</h3>
          {stats ? (
            <div className="stats-grid">
              <div className="stats-item">
                <span className="stats-name">Total Official:</span>
                <span className="stats-val">{stats.Summary?.Total_Official || 0}</span>
              </div>
              <div className="stats-item">
                <span className="stats-name green-text">Perfect Match:</span>
                <span className="stats-val">{stats.Summary?.PerfectMatch || 0}</span>
              </div>
              <div className="stats-item">
                <span className="stats-name yellow-text">Changed / Diff:</span>
                <span className="stats-val">{stats.Summary?.Changed || 0}</span>
              </div>
              <div className="stats-item">
                <span className="stats-name red-text">Missing in OSM:</span>
                <span className="stats-val">{stats.Summary?.MissingInOSM || 0}</span>
              </div>
              <div className="stats-item">
                <span className="stats-name blue-text">New in OSM:</span>
                <span className="stats-val">{stats.Summary?.NewInOSM || 0}</span>
              </div>

              {/* Render charts generated by stats.py */}
              <div className="visuals-container">
                <h4>Status Chart</h4>
                <img 
                  src="http://localhost:8000/static/statistics/status_pie_chart.png" 
                  alt="Pie Chart" 
                  onError={(e) => { e.currentTarget.style.display = 'none'; }}
                />
                <h4>Overlap Distribution</h4>
                <img 
                  src="http://localhost:8000/static/statistics/overlap_histogram.png" 
                  alt="Histogram" 
                  onError={(e) => { e.currentTarget.style.display = 'none'; }}
                />
              </div>
            </div>
          ) : (
            <p className="loading-text">Run pipeline.py and start API backend to load stats...</p>
          )}
        </div>
      </div>
      
      <div className="map-container" ref={mapElement}></div>

      {/* Map Popup Overlay */}
      <div className="ol-popup" ref={popupElement}>
        {selectedFeature && (
          <div className="popup-content">
            <h4>Feature Details</h4>
            
            {/* If it's a difference feature */}
            {selectedFeature.fillColor && (
              <>
                <p><strong>Official Name:</strong> {selectedFeature.a03_ten || 'N/A'}</p>
                <p><strong>OSM Name:</strong> {selectedFeature.osm_name || 'N/A'}</p>
                <p><strong>Official ID:</strong> {selectedFeature.official_id || 'N/A'}</p>
                <p><strong>OSM ID:</strong> {selectedFeature.osm_id || 'N/A'}</p>
                <p><strong>Category:</strong> <span className="cat-pill" style={{backgroundColor: selectedFeature.fillColor}}>{selectedFeature.category || 'N/A'}</span></p>
                <p><strong>Overlap Ratio:</strong> {selectedFeature.overlap_ratio ? `${(selectedFeature.overlap_ratio * 100).toFixed(2)}%` : 'N/A'}</p>
                <p><strong>IoU (Overlap):</strong> {selectedFeature.iou ? `${(selectedFeature.iou * 100).toFixed(2)}%` : 'N/A'}</p>
              </>
            )}

            {/* If it's a missing feature */}
            {selectedFeature.category === "Missing in OSM" && (
              <>
                <p><strong>Official Name:</strong> {selectedFeature.official_name || 'N/A'}</p>
                <p><strong>Province:</strong> {selectedFeature.province || 'N/A'}</p>
                <p><strong>Official ID:</strong> {selectedFeature.official_id || 'N/A'}</p>
                <p><strong>Category:</strong> <span className="cat-pill red-pill">{selectedFeature.category}</span></p>
              </>
            )}

            {/* If it's a new feature */}
            {selectedFeature.category === "New in OSM" && (
              <>
                <p><strong>OSM Name:</strong> {selectedFeature.osm_name || 'N/A'}</p>
                <p><strong>OSM ID:</strong> {selectedFeature.osm_id || 'N/A'}</p>
                <p><strong>Category:</strong> <span className="cat-pill blue-pill">{selectedFeature.category}</span></p>
              </>
            )}

            {/* Default fallback */}
            {!selectedFeature.category && (
              <>
                <p><strong>Name:</strong> {selectedFeature.name || selectedFeature.a03_ten || 'N/A'}</p>
                <p><strong>ID:</strong> {selectedFeature.id || selectedFeature.a02_xa || 'N/A'}</p>
                {selectedFeature.a04_tentinh && <p><strong>Province:</strong> {selectedFeature.a04_tentinh}</p>}
              </>
            )}
            
            <hr />
            <div className="popup-actions">
              <strong>Quick Actions:</strong>
              <div className="action-row">
                <button className="action-btn" onClick={() => alert("Marked to Keep OSM")}>Keep OSM</button>
                <button className="action-btn primary" onClick={() => alert("Marked to Update Geometry")}>Update Geometry</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default App
