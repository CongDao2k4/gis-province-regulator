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
  const [admLevel, setAdmLevel] = useState<'commune' | 'province'>('commune')

  const refreshData = () => {
    const apiBase = admLevel === 'province' ? 'http://localhost:8000/tinh' : 'http://localhost:8000'
    
    fetch(`${apiBase}/statistics`)
      .then(res => res.json())
      .then(data => setStats(data))
      .catch(err => console.error("Error fetching stats:", err))

    fetch(`${apiBase}/candidates/metadata`)
      .then(res => res.json())
      .then(data => setCandidates(data))
      .catch(err => console.error("Error fetching candidates:", err))
  }

  // 1. Fetch initial statistics and candidates metadata
  useEffect(() => {
    refreshData()
  }, [admLevel])

  const handleLevelChange = (level: 'commune' | 'province') => {
    setAdmLevel(level)
    setSelectedCandidate(null)
    if (activeSourceRef.current) {
      activeSourceRef.current.clear()
    }
  }

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
          fill: new Fill({ color: 'rgba(16, 185, 129, 0.12)' }),
          stroke: new Stroke({ color: '#10b981', width: 2.5 })
        })
      } else if (type === 'osm') {
        return new Style({
          fill: new Fill({ color: 'rgba(59, 130, 246, 0.12)' }),
          stroke: new Stroke({ color: '#3b82f6', width: 2.5 })
        })
      } else if (type === 'difference') {
        const fillColorVal = feature.get('fillColor')
        let fillColor = 'rgba(239, 68, 68, 0.65)' // red: excess OSM (Only in OSM)
        let strokeColor = '#ef4444'
        
        if (fillColorVal === 'purple' || fillColorVal === 'blue') {
          fillColor = 'rgba(168, 85, 247, 0.65)' // purple: missing on OSM (Only in Official) / shape changed
          strokeColor = '#a855f7'
        } else if (fillColorVal === 'yellow') {
          fillColor = 'rgba(241, 196, 15, 0.35)' // yellow: intersection
          strokeColor = '#f1c40f'
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

    const apiBase = admLevel === 'province' ? 'http://localhost:8000/tinh' : 'http://localhost:8000'
    fetch(`${apiBase}/candidate/${candidate.official_id}/geometry?osm_id=${candidate.osm_id}`)
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
        }
        // Zoom to the extent of loaded geometries
        const extent = activeSourceRef.current?.getExtent()
        if (extent && extent[0] !== Infinity && extent[0] !== -Infinity) {
          mapRef.current?.getView().fit(extent, {
            duration: 800,
            padding: [100, 100, 100, 100],
            maxZoom: 14
          })
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

    const syncUrl = admLevel === 'province' 
      ? 'http://localhost:8000/tinh/api/edit-tinh' 
      : 'http://localhost:8000/api/edit-osm'

    fetch(syncUrl, {
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
        setSelectedCandidate(null)
        if (activeSourceRef.current) activeSourceRef.current.clear()
        refreshData() // Reload backend statistics and metadata candidates
      })
      .catch(err => {
        console.error("OSM sync error:", err)
      })
  }

  // Filter candidates based on active tab
  const filteredCandidates = candidates.filter(c => {
    const isTabMatch =
      activeTab === 'add' ? c.category === 'Missing' :
        activeTab === 'delete' ? c.category === 'New' :
          activeTab === 'matched' ? c.category === 'Matched' :
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

        {/* Administrative Level Toggle Switch */}
        <div className="level-toggle-container" style={{ display: 'flex', gap: '8px', padding: '6px 8px', background: 'rgba(255,255,255,0.03)', borderRadius: '8px', marginBottom: '16px', border: '1px solid rgba(255,255,255,0.08)' }}>
          <button
            onClick={() => handleLevelChange('commune')}
            style={{
              flex: 1,
              padding: '8px 12px',
              borderRadius: '6px',
              border: 'none',
              background: admLevel === 'commune' ? '#10b981' : 'transparent',
              color: admLevel === 'commune' ? '#fff' : '#8a99ad',
              fontWeight: '600',
              cursor: 'pointer',
              transition: 'all 0.2s',
              fontSize: '12px'
            }}
          >
            🇻🇳 Xã/Phường
          </button>
          <button
            onClick={() => handleLevelChange('province')}
            style={{
              flex: 1,
              padding: '8px 12px',
              borderRadius: '6px',
              border: 'none',
              background: admLevel === 'province' ? '#10b981' : 'transparent',
              color: admLevel === 'province' ? '#fff' : '#8a99ad',
              fontWeight: '600',
              cursor: 'pointer',
              transition: 'all 0.2s',
              fontSize: '12px'
            }}
          >
            🗺️ Tỉnh/Quốc Gia
          </button>
        </div>

        {/* Tab Selection */}
        <div className="tab-container" style={{ display: 'flex', gap: '4px', marginBottom: '16px', flexWrap: 'wrap' }}>
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
          <button
            className={`tab-btn ${activeTab === 'matched' ? 'active' : ''}`}
            onClick={() => { setActiveTab('matched'); setSelectedCandidate(null); }}
            style={tabButtonStyle(activeTab === 'matched')}
          >
            ✔️ Khớp ({candidates.filter(c => c.category === 'Matched').length})
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
            <span style={{ display: 'inline-block', width: '12px', height: '12px', border: '2px solid #10b981', backgroundColor: 'rgba(16, 185, 129, 0.15)', borderRadius: '2px' }}></span>
            <span>Ranh giới Official (Nhà nước)</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', marginTop: '6px' }}>
            <span style={{ display: 'inline-block', width: '12px', height: '12px', border: '2px dashed #3b82f6', backgroundColor: 'rgba(59, 130, 246, 0.15)', borderRadius: '2px' }}></span>
            <span>Ranh giới OSM hiện tại</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', marginTop: '6px' }}>
            <span style={{ display: 'inline-block', width: '12px', height: '12px', backgroundColor: 'rgba(239, 68, 68, 0.65)', borderRadius: '2px' }}></span>
            <span>Phần ranh giới OSM thừa (Cần cắt)</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', marginTop: '6px' }}>
            <span style={{ display: 'inline-block', width: '12px', height: '12px', backgroundColor: 'rgba(168, 85, 247, 0.65)', borderRadius: '2px' }}></span>
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
