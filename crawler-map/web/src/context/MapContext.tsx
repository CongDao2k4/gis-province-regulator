import { createContext, useContext, useState, useRef, useEffect, useCallback } from 'react'
import type { ReactNode } from 'react'
import Map from 'ol/Map'
import GeoJSON from 'ol/format/GeoJSON'
import type VectorLayer from 'ol/layer/Vector'
import type TileLayer from 'ol/layer/Tile'

// ── Types ──────────────────────────────────────────────────────────
export interface LayerState {
  osmBase: boolean
  official: boolean
  osmBoundary: boolean
  difference: boolean
  missing: boolean
  newBoundary: boolean
}

export interface OpacityState {
  osmBase: number
  official: number
  osmBoundary: number
  difference: number
  missing: number
  newBoundary: number
}

export interface CompareResult {
  official_id: string
  official_name: string
  province: string
  osm_id: string
  osm_name: string
  area_official_sqm: number
  area_osm_sqm: number
  area_difference_sqm: number
  intersect_area_sqm: number
  overlap_ratio: number
  iou: number
  hausdorff: number
  name_similarity: number
}

export interface ToastMessage {
  id: number
  text: string
  type: 'success' | 'error' | 'info'
}

export type ActivePanel = 'layers' | 'stats' | 'review' | 'table' | 'export' | 'ai'

// ── Layer config (colors, labels) ──────────────────────────────────
export const LAYER_CONFIG = [
  { id: 'osmBase', label: 'Base Map (OSM)', color: '#94a3b8', strokeColor: '#94a3b8' },
  { id: 'official', label: 'Official Boundary', color: '#f97316', strokeColor: '#f97316' },
  { id: 'osmBoundary', label: 'OSM Boundary', color: '#38bdf8', strokeColor: '#38bdf8' },
  { id: 'difference', label: 'Difference Areas', color: '#ef4444', strokeColor: '#ef4444' },
  { id: 'missing', label: 'Missing (Official)', color: '#a855f7', strokeColor: '#a855f7' },
  { id: 'newBoundary', label: 'New (OSM only)', color: '#eab308', strokeColor: '#eab308' },
] as const

// ── Context value ──────────────────────────────────────────────────
interface MapContextType {
  // Map
  map: Map | null
  setMap: (m: Map | null) => void
  layerRefs: React.MutableRefObject<Record<string, TileLayer<any> | VectorLayer<any>>>

  // Layer state
  layers: LayerState
  setLayers: React.Dispatch<React.SetStateAction<LayerState>>
  opacities: OpacityState
  setOpacities: React.Dispatch<React.SetStateAction<OpacityState>>
  toggleLayer: (key: keyof LayerState) => void
  changeOpacity: (key: keyof OpacityState, val: number) => void

  // Feature
  selectedFeature: any
  setSelectedFeature: (f: any) => void
  highlightedId: string | null
  setHighlightedId: (id: string | null) => void

  // Data
  stats: any
  compareResults: CompareResult[]
  isLoading: boolean

  // Panel
  activePanel: ActivePanel
  setActivePanel: (p: ActivePanel) => void
  reviewPanelOpen: boolean
  setReviewPanelOpen: (b: boolean) => void
  compareMode: boolean
  setCompareMode: (b: boolean) => void

  // Actions
  zoomToFeature: (feat: any) => void
  zoomToLayerExtent: (layerKey: string) => void
  showToast: (text: string, type?: 'success' | 'error' | 'info') => void
  toasts: ToastMessage[]
  removeToast: (id: number) => void
}

const MapContext = createContext<MapContextType | null>(null)

export function useMapContext() {
  const ctx = useContext(MapContext)
  if (!ctx) throw new Error('useMapContext must be inside MapProvider')
  return ctx
}

// ── Provider ───────────────────────────────────────────────────────
export function MapProvider({ children }: { children: ReactNode }) {
  const [map, setMap] = useState<Map | null>(null)
  const layerRefs = useRef<Record<string, TileLayer<any> | VectorLayer<any>>>({})

  const [layers, setLayers] = useState<LayerState>({
    osmBase: true,
    official: true,
    osmBoundary: false,
    difference: true,
    missing: true,
    newBoundary: true,
  })

  const [opacities, setOpacities] = useState<OpacityState>({
    osmBase: 1.0,
    official: 0.6,
    osmBoundary: 0.6,
    difference: 0.8,
    missing: 0.8,
    newBoundary: 0.8,
  })

  const [selectedFeature, setSelectedFeature] = useState<any>(null)
  const [highlightedId, setHighlightedId] = useState<string | null>(null)
  const [stats, setStats] = useState<any>(null)
  const [compareResults, setCompareResults] = useState<CompareResult[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [activePanel, setActivePanel] = useState<ActivePanel>('layers')
  const [reviewPanelOpen, setReviewPanelOpen] = useState(false)
  const [compareMode, setCompareMode] = useState(false)
  const [toasts, setToasts] = useState<ToastMessage[]>([])
  const toastId = useRef(0)

  // ── Fetch data on mount ──
  useEffect(() => {
    setIsLoading(true)
    Promise.all([
      fetch('http://localhost:8000/statistics').then(r => r.json()).catch(() => null),
      fetch('http://localhost:8000/compare-results').then(r => r.json()).catch(() => []),
    ]).then(([s, cr]) => {
      setStats(s)
      setCompareResults(Array.isArray(cr) ? cr : [])
      setIsLoading(false)
    })
  }, [])

  // ── Sync layer visibility ──
  useEffect(() => {
    Object.keys(layers).forEach(key => {
      const layer = layerRefs.current[key]
      if (layer) layer.setVisible(layers[key as keyof LayerState])
    })
  }, [layers])

  // ── Sync layer opacity ──
  useEffect(() => {
    Object.keys(opacities).forEach(key => {
      const layer = layerRefs.current[key]
      if (layer) layer.setOpacity(opacities[key as keyof OpacityState])
    })
  }, [opacities])

  // ── Compare mode ──
  useEffect(() => {
    if (compareMode) {
      setLayers(prev => ({ ...prev, official: true, osmBoundary: true, difference: true }))
    }
  }, [compareMode])

  const toggleLayer = useCallback((key: keyof LayerState) => {
    setLayers(prev => ({ ...prev, [key]: !prev[key] }))
  }, [])

  const changeOpacity = useCallback((key: keyof OpacityState, val: number) => {
    setOpacities(prev => ({ ...prev, [key]: val }))
  }, [])

  const zoomToFeature = useCallback((feat: any) => {
    if (!map) return
    try {
      const format = new GeoJSON()
      const olFeature = format.readFeature(feat, {
        dataProjection: 'EPSG:4326',
        featureProjection: 'EPSG:3857',
      })
      const geom = olFeature.getGeometry()
      if (geom) {
        map.getView().fit(geom.getExtent(), {
          duration: 800,
          padding: [100, 100, 100, 100],
          maxZoom: 15,
        })
      }
    } catch {
      // feature might already be in 3857 or not have geometry
    }
  }, [map])

  const zoomToLayerExtent = useCallback((layerKey: string) => {
    if (!map) return
    const layer = layerRefs.current[layerKey]
    if (layer && 'getSource' in layer) {
      const source = (layer as VectorLayer<any>).getSource()
      if (source) {
        const extent = source.getExtent()
        if (extent && extent[0] !== Infinity) {
          map.getView().fit(extent, { duration: 800, padding: [50, 50, 50, 50], maxZoom: 14 })
        }
      }
    }
  }, [map])

  const showToast = useCallback((text: string, type: 'success' | 'error' | 'info' = 'info') => {
    const id = ++toastId.current
    setToasts(prev => [...prev, { id, text, type }])
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 3500)
  }, [])

  const removeToast = useCallback((id: number) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  return (
    <MapContext.Provider value={{
      map, setMap, layerRefs,
      layers, setLayers, opacities, setOpacities, toggleLayer, changeOpacity,
      selectedFeature, setSelectedFeature, highlightedId, setHighlightedId,
      stats, compareResults, isLoading,
      activePanel, setActivePanel, reviewPanelOpen, setReviewPanelOpen,
      compareMode, setCompareMode,
      zoomToFeature, zoomToLayerExtent,
      showToast, toasts, removeToast,
    }}>
      {children}
    </MapContext.Provider>
  )
}
