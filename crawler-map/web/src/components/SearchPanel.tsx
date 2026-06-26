import { useState, useCallback } from 'react'
import GeoJSON from 'ol/format/GeoJSON'
import { useMapContext } from '../context/MapContext'

export default function SearchPanel() {
  const { map, setSelectedFeature, showToast } = useMapContext()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<any[]>([])
  const [searching, setSearching] = useState(false)

  const handleSearch = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value
    setQuery(val)

    if (val.trim().length >= 2) {
      setSearching(true)
      fetch(`http://localhost:8000/search?q=${encodeURIComponent(val)}`)
        .then(r => r.json())
        .then(data => {
          setResults(data.features || [])
          setSearching(false)
        })
        .catch(() => {
          setResults([])
          setSearching(false)
        })
    } else {
      setResults([])
    }
  }, [])

  const selectFeature = useCallback((feat: any) => {
    if (!map) return
    try {
      const format = new GeoJSON()
      const olFeature = format.readFeature(feat, {
        dataProjection: 'EPSG:4326',
        featureProjection: 'EPSG:3857',
      })
      const geom = olFeature.getGeometry()
      if (geom) {
        const extent = geom.getExtent()
        map.getView().fit(extent, {
          duration: 1000,
          padding: [100, 100, 100, 100],
          maxZoom: 14,
        })

        // Set popup position
        const center = [(extent[0] + extent[2]) / 2, (extent[1] + extent[3]) / 2]
        const popup = map.getOverlays().getArray()[0]
        if (popup) popup.setPosition(center)

        setSelectedFeature(feat.properties)
        showToast(`Zoom to: ${feat.properties.a03_ten || feat.properties.name}`, 'info')
      }
    } catch {
      // skip
    }
    setResults([])
    setQuery('')
  }, [map, setSelectedFeature, showToast])

  return (
    <div className="sidebar-section search-section">
      <h3>🔍 Search Communes</h3>
      <div className="search-box">
        <input
          type="text"
          placeholder="Tìm tên xã / phường..."
          value={query}
          onChange={handleSearch}
        />
        {searching && <div className="search-spinner">⏳</div>}
        {results.length > 0 && (
          <ul className="search-results">
            {results.slice(0, 30).map((feat, i) => (
              <li key={i} onClick={() => selectFeature(feat)}>
                <span>{feat.properties.a03_ten || feat.properties.name || feat.properties.official_name}</span>
                <span className="result-prov">
                  {feat.properties.a04_tentinh || feat.properties.province || ''}
                </span>
              </li>
            ))}
            {results.length > 30 && (
              <li className="more-results">...và {results.length - 30} kết quả khác</li>
            )}
          </ul>
        )}
      </div>
    </div>
  )
}
