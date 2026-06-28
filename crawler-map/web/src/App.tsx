import { useEffect, useRef, useState } from 'react'
import Map from 'ol/Map'
import View from 'ol/View'
import TileLayer from 'ol/layer/Tile'
import OSM from 'ol/source/OSM'
import VectorLayer from 'ol/layer/Vector'
import VectorSource from 'ol/source/Vector'
import GeoJSON from 'ol/format/GeoJSON'
import { Style, Fill, Stroke } from 'ol/style'
import 'ol/ol.css'
import './App.css'

interface Candidate {
  official_id: string;
  official_name: string;
  province: string;
  osm_id: string;
  osm_name: string;
  category: string;
  overlap_ratio: number;
  name_similarity: number;
  reason: string;
}

function App() {
  const mapElement = useRef<HTMLDivElement>(null)
  const mapRef = useRef<Map | null>(null)
  const activeSourceRef = useRef<VectorSource | null>(null)
  
  const [stats, setStats] = useState<any>(null)
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [selectedCandidate, setSelectedCandidate] = useState<Candidate | null>(null)
  const [activeTab, setActiveTab] = useState<'edit' | 'add' | 'delete'>('edit')
  const [loadingGeom, setLoadingGeom] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')

  // 1. Fetch initial statistics and candidates metadata (extremely lightweight)
  useEffect(() => {
    fetch('http://localhost:8000/statistics')
      .then(res => res.json())
      .then(data => setStats(data))
      .catch(err => console.error("Error fetching stats:", err))

    fetch('http://localhost:8000/candidates/metadata')
      .then(res => res.json())
      .then(data => setCandidates(data))
      .catch(err => console.error("Error fetching candidates:", err))
  }, [])

  // 2. Initialize Map (only base OSM layer + active vector layer for selection)
  useEffect(() => {
    if (!mapElement.current) return;

    const osmBaseLayer = new TileLayer({
      source: new OSM(),
      opacity: 0.9
    })

    const activeSource = new VectorSource()
    activeSourceRef.current = activeSource

    // Style function to render Official boundary, OSM boundary, and differences with unique styles
    const activeSelectedStyleFunc = (feature: any) => {
      const type = feature.get('layerType')
      if (type === 'official') {
        return new Style({
          fill: new Fill({ color: 'rgba(52, 152, 219, 0.12)' }),
          stroke: new Stroke({ color: '#3498db', width: 2.5 })
        })
      } else if (type === 'osm') {
        return new Style({
          fill: new Fill({ color: 'rgba(46, 204, 113, 0.12)' }),
          stroke: new Stroke({ color: '#2ecc71', width: 2.5 })
        })
      } else if (type === 'difference') {
        const fillColorVal = feature.get('fillColor')
        let fillColor = 'rgba(231, 76, 60, 0.45)' // red: excess OSM
        let strokeColor = '#e74c3c'
        
        if (fillColorVal === 'blue') {
          fillColor = 'rgba(52, 152, 219, 0.45)' // blue: missing on OSM
          strokeColor = '#3498db'
        } else if (fillColorVal === 'yellow') {
          fillColor = 'rgba(241, 196, 15, 0.35)' // yellow: intersection
          strokeColor = '#f1c40f'
        } else if (fillColorVal === 'purple') {
          fillColor = 'rgba(155, 89, 182, 0.45)' // purple: shape changed
          strokeColor = '#9b59b6'
        }
        
        return new Style({
          fill: new Fill({ color: fillColor }),
          stroke: new Stroke({ color: strokeColor, width: 1.5 })
        })
      }
      return new Style({})
    }

    const activeSelectedLayer = new VectorLayer({
      source: activeSource,
      style: activeSelectedStyleFunc
    })

    const map = new Map({
      target: mapElement.current,
      layers: [osmBaseLayer, activeSelectedLayer],
      view: new View({
        center: [12000000, 1800000], // Centered around Vietnam
        zoom: 6
      })
    })

    mapRef.current = map

    return () => {
      map.setTarget(undefined)
    }
  }, [])

  // 3. Load geometry for the selected candidate on-demand (Fast O(1) fetch)
  const handleSelectCandidate = (candidate: Candidate) => {
    setSelectedCandidate(candidate)
    if (!activeSourceRef.current || !mapRef.current) return;

    setLoadingGeom(true)
    activeSourceRef.current.clear()

    fetch(`http://localhost:8000/candidate/${candidate.official_id}/geometry?osm_id=${candidate.osm_id}`)
      .then(res => res.json())
      .then(data => {
        const format = new GeoJSON()
        const features: any[] = []

        // Parse official geometry
        if (data.official) {
          const feat = format.readFeature(data.official, {
            dataProjection: 'EPSG:4326',
            featureProjection: 'EPSG:3857'
          })
          feat.set('layerType', 'official')
          features.push(feat)
        }

        // Parse OSM geometry
        if (data.osm) {
          const feat = format.readFeature(data.osm, {
            dataProjection: 'EPSG:4326',
            featureProjection: 'EPSG:3857'
          })
          feat.set('layerType', 'osm')
          features.push(feat)
        }

        // Parse difference geometries
        if (data.difference && data.difference.features) {
          data.difference.features.forEach((f: any) => {
            const feat = format.readFeature(f, {
              dataProjection: 'EPSG:4326',
              featureProjection: 'EPSG:3857'
            })
            feat.set('layerType', 'difference')
            features.push(feat)
          })
        }

        if (activeSourceRef.current) {
          activeSourceRef.current.addFeatures(features)
          const extent = activeSourceRef.current.getExtent()
          if (extent && extent[0] !== Infinity && extent[0] !== -Infinity) {
            mapRef.current.getView().fit(extent, {
              duration: 800,
              padding: [80, 80, 80, 80],
              maxZoom: 15
            })
          }
        }
        setLoadingGeom(false)
      })
      .catch(err => {
        console.error("Error loading candidate geometries:", err)
        setLoadingGeom(false)
      })
  }

  // 4. Synchronize modifications to OSM database (Simulated OSM API request)
  const handleSyncToOSM = () => {
    if (!selectedCandidate) return;

    const action = activeTab === 'add' ? 'create' : (activeTab === 'delete' ? 'delete' : 'modify');
    
    fetch('http://localhost:8000/api/edit-osm', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        official_id: selectedCandidate.official_id,
        osm_id: selectedCandidate.osm_id,
        action: action
      })
    })
      .then(res => res.json())
      .then(data => {
        alert(data.message)
      })
      .catch(err => {
        console.error("OSM sync error:", err)
        alert("Có lỗi xảy ra khi đồng bộ lên OSM.")
      })
  }

  // Filter candidates based on active tab
  const filteredCandidates = candidates.filter(c => {
    const isTabMatch = 
      activeTab === 'add' ? c.category === 'Missing' :
      activeTab === 'delete' ? c.category === 'New' :
      (c.category === 'Need Update' || c.category === 'Need Review');
      
    if (!isTabMatch) return false;

    // Optional name search filter
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      const name = (c.official_name || c.osm_name || '').toLowerCase()
      return name.includes(q)
    }
    return true;
  })

  return (
    <div className="app-container dark-theme">
      {/* Sidebar Panel */}
      <div className="sidebar" style={{ display: 'flex', flexDirection: 'column' }}>
        <div className="logo-section">
          <h2>GIS REGULATOR</h2>
          <span className="subtitle font-outfit">OSM Boundary Normalization</span>
        </div>

        {/* Tab Selection */}
        <div className="tab-container" style={{ display: 'flex', gap: '4px', marginBottom: '16px' }}>
          <button 
            className={`tab-btn ${activeTab === 'edit' ? 'active' : ''}`}
            onClick={() => { setActiveTab('edit'); setSelectedCandidate(null); }}
            style={tabButtonStyle(activeTab === 'edit')}
          >
            ✏️ Sửa ({candidates.filter(c => c.category === 'Need Update' || c.category === 'Need Review').length})
          </button>
          <button 
            className={`tab-btn ${activeTab === 'add' ? 'active' : ''}`}
            onClick={() => { setActiveTab('add'); setSelectedCandidate(null); }}
            style={tabButtonStyle(activeTab === 'add')}
          >
            ➕ Thêm ({candidates.filter(c => c.category === 'Missing').length})
          </button>
          <button 
            className={`tab-btn ${activeTab === 'delete' ? 'active' : ''}`}
            onClick={() => { setActiveTab('delete'); setSelectedCandidate(null); }}
            style={tabButtonStyle(activeTab === 'delete')}
          >
            🗑️ Xóa ({candidates.filter(c => c.category === 'New').length})
          </button>
        </div>

        {/* Search filter in tab */}
        <div style={{ marginBottom: '12px' }}>
          <input
            type="text"
            placeholder="Tìm kiếm theo tên..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={inputStyle}
          />
        </div>

        {/* Candidate List */}
        <div style={{ flexGrow: 1, overflowY: 'auto', marginBottom: '16px' }} className="candidate-list-scroll">
          {filteredCandidates.length === 0 ? (
            <p style={{ color: 'var(--text-muted)', fontSize: '13px', textAlign: 'center', marginTop: '20px' }}>
              Không tìm thấy mục nào.
            </p>
          ) : (
            filteredCandidates.map((c, i) => (
              <div 
                key={i} 
                onClick={() => handleSelectCandidate(c)}
                style={candidateItemStyle(selectedCandidate?.official_id === c.official_id && selectedCandidate?.osm_id === c.osm_id)}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <strong style={{ fontSize: '14px', color: 'var(--text-main)' }}>
                    {c.official_name !== 'N/A' ? c.official_name : c.osm_name}
                  </strong>
                  {c.overlap_ratio > 0 && (
                    <span style={{ fontSize: '11px', color: 'var(--accent-yellow)', background: 'rgba(251, 191, 36, 0.1)', padding: '2px 6px', borderRadius: '4px' }}>
                      {Math.round(c.overlap_ratio * 100)}% trùng
                    </span>
                  )}
                </div>
                <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginTop: '4px' }}>
                  {c.province !== 'N/A' ? c.province : 'Chỉ có trên OSM'}
                </div>
              </div>
            ))
          )}
        </div>

        {/* Statistics section */}
        {stats && (
          <div style={{ background: 'rgba(0,0,0,0.2)', border: '1px solid var(--border-color)', borderRadius: '8px', padding: '10px', fontSize: '12px', color: 'var(--text-muted)' }}>
            <strong>Tỷ lệ tổng quát:</strong> Khớp {stats.Summary?.perfect_match} | Lệch {stats.Summary?.need_update} | Thiếu {stats.Summary?.need_add} | Thừa {stats.Summary?.need_delete}
          </div>
        )}
      </div>

      {/* Main Map Container */}
      <div className="map-container" ref={mapElement} style={{ flexGrow: 1, position: 'relative' }}>
        {loadingGeom && (
          <div style={loadingOverlayStyle}>
            <span style={{ fontSize: '14px', color: '#fff' }}>🔄 Đang tải ranh giới địa lý...</span>
          </div>
        )}

        {/* Floating details panel for selected Candidate */}
        {selectedCandidate && (
          <div style={detailsPanelStyle}>
            <h4 style={{ margin: '0 0 10px 0', borderBottom: '1px solid var(--border-color)', paddingBottom: '6px', color: 'var(--accent-blue)', fontSize: '16px' }}>
              Chi Tiết Vùng Đối Soát
            </h4>
            <p style={detailRowStyle}><strong>Tên Official:</strong> {selectedCandidate.official_name}</p>
            <p style={detailRowStyle}><strong>Tên OSM:</strong> {selectedCandidate.osm_name}</p>
            <p style={detailRowStyle}><strong>Mã Official ID:</strong> {selectedCandidate.official_id}</p>
            <p style={detailRowStyle}>
              <strong>Mã OSM ID:</strong> {selectedCandidate.osm_id}{' '}
              {selectedCandidate.osm_id !== 'N/A' && (
                <a
                  href={`https://www.openstreetmap.org/relation/${selectedCandidate.osm_id}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{ color: 'var(--accent-blue)', textDecoration: 'underline', marginLeft: '5px' }}
                >
                  (Xem trên OSM)
                </a>
              )}
            </p>
            <p style={detailRowStyle}><strong>Tỉnh/TP:</strong> {selectedCandidate.province}</p>
            <p style={detailRowStyle}><strong>Lý do hành động:</strong> <span style={{ color: 'var(--accent-yellow)' }}>{selectedCandidate.reason}</span></p>

            <div style={{ marginTop: '16px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <button 
                onClick={handleSyncToOSM}
                style={syncButtonStyle(activeTab === 'delete' ? 'delete' : (activeTab === 'add' ? 'add' : 'edit'))}
              >
                {activeTab === 'add' ? '➕ Đồng bộ Thêm mới lên OSM' : (activeTab === 'delete' ? '🗑️ Đồng bộ Xóa khỏi OSM' : '✏️ Đồng bộ Chỉnh sửa lên OSM')}
              </button>
            </div>
          </div>
        )}

        {/* Color Legend overlay */}
        <div style={legendStyle}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px' }}>
            <span style={{ display: 'inline-block', width: '12px', height: '12px', border: '2px solid #3498db', backgroundColor: 'rgba(52, 152, 219, 0.15)', borderRadius: '2px' }}></span>
            <span>Ranh giới Official (Nhà nước)</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', marginTop: '6px' }}>
            <span style={{ display: 'inline-block', width: '12px', height: '12px', border: '2px solid #2ecc71', backgroundColor: 'rgba(46, 204, 113, 0.15)', borderRadius: '2px' }}></span>
            <span>Ranh giới OSM hiện tại</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', marginTop: '6px' }}>
            <span style={{ display: 'inline-block', width: '12px', height: '12px', backgroundColor: 'rgba(231, 76, 60, 0.65)', borderRadius: '2px' }}></span>
            <span>Phần ranh giới OSM thừa (Cần cắt)</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', marginTop: '6px' }}>
            <span style={{ display: 'inline-block', width: '12px', height: '12px', backgroundColor: 'rgba(52, 152, 219, 0.65)', borderRadius: '2px' }}></span>
            <span>Phần ranh giới OSM thiếu (Cần bù)</span>
          </div>
        </div>
      </div>
    </div>
  )
}

// Inline Styles for simplicity and premium UI
const tabButtonStyle = (isActive: boolean) => ({
  flex: 1,
  padding: '10px 4px',
  background: isActive ? 'rgba(56, 189, 248, 0.2)' : 'rgba(0, 0, 0, 0.3)',
  border: `1px solid ${isActive ? 'var(--accent-blue)' : 'var(--border-color)'}`,
  borderRadius: '6px',
  color: isActive ? 'var(--accent-blue)' : 'var(--text-muted)',
  cursor: 'pointer',
  fontSize: '12.5px',
  fontWeight: isActive ? '600' : '400',
  transition: 'all 0.2s',
  textAlign: 'center' as const
})

const inputStyle = {
  width: '100%',
  padding: '8px 12px',
  background: 'rgba(0,0,0,0.3)',
  border: '1px solid var(--border-color)',
  borderRadius: '6px',
  color: 'var(--text-main)',
  fontFamily: 'inherit',
  fontSize: '13px',
  boxSizing: 'border-box' as const
}

const candidateItemStyle = (isSelected: boolean) => ({
  padding: '12px',
  background: isSelected ? 'rgba(56, 189, 248, 0.12)' : 'rgba(255,255,255,0.01)',
  border: `1px solid ${isSelected ? 'var(--accent-blue)' : 'var(--border-color)'}`,
  borderRadius: '8px',
  cursor: 'pointer',
  marginBottom: '8px',
  transition: 'all 0.2s'
})

const loadingOverlayStyle = {
  position: 'absolute' as const,
  top: '20px',
  left: '50%',
  transform: 'translateX(-50%)',
  background: 'rgba(15, 23, 42, 0.85)',
  padding: '10px 20px',
  borderRadius: '24px',
  zIndex: 1000,
  border: '1px solid var(--border-color)',
  boxShadow: '0 4px 12px rgba(0,0,0,0.5)',
  backdropFilter: 'blur(8px)'
}

const detailsPanelStyle = {
  position: 'absolute' as const,
  top: '20px',
  right: '20px',
  background: 'rgba(15, 23, 42, 0.9)',
  border: '1px solid var(--border-color)',
  boxShadow: '0 10px 30px rgba(0, 0, 0, 0.6)',
  padding: '20px',
  borderRadius: '12px',
  width: '320px',
  zIndex: 100,
  color: 'var(--text-main)',
  backdropFilter: 'blur(16px)',
  maxHeight: '85%',
  overflowY: 'auto' as const
}

const legendStyle = {
  position: 'absolute' as const,
  bottom: '20px',
  right: '20px',
  background: 'rgba(15, 23, 42, 0.9)',
  border: '1px solid var(--border-color)',
  boxShadow: '0 4px 15px rgba(0, 0, 0, 0.4)',
  padding: '12px 16px',
  borderRadius: '8px',
  zIndex: 100,
  color: 'var(--text-main)',
  backdropFilter: 'blur(8px)'
}

const detailRowStyle = {
  margin: '8px 0',
  fontSize: '13px',
  lineHeight: '1.4'
}

const syncButtonStyle = (type: 'add' | 'delete' | 'edit') => {
  const color = 
    type === 'add' ? 'var(--accent-green)' :
    type === 'delete' ? 'var(--accent-red)' :
    'var(--accent-blue)';
    
  return {
    width: '100%',
    padding: '10px',
    background: color,
    border: `1px solid ${color}`,
    borderRadius: '6px',
    color: '#0b0f19',
    fontWeight: '700',
    fontSize: '13px',
    cursor: 'pointer',
    boxShadow: `0 4px 10px rgba(0, 0, 0, 0.2)`,
    transition: 'all 0.2s'
  }
}

export default App
