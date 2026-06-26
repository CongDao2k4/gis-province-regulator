import { useMapContext, LAYER_CONFIG } from '../context/MapContext'
import type { LayerState, OpacityState } from '../context/MapContext'

export default function LayerManager() {
  const {
    layers, toggleLayer, opacities, changeOpacity,
    zoomToLayerExtent, compareMode, setCompareMode,
  } = useMapContext()

  return (
    <div className="sidebar-section layer-control-section">
      <h3>🗺️ Layer Control</h3>

      {/* Compare Mode Toggle (promptui08) */}
      <div className="compare-mode-toggle">
        <label className="checkbox-container">
          <input
            type="checkbox"
            checked={compareMode}
            onChange={() => setCompareMode(!compareMode)}
          />
          <span className="checkmark" style={{ borderColor: '#c084fc' }} />
          <span className="layer-label">⚡ Compare Mode</span>
        </label>
        {compareMode && (
          <span className="compare-badge">OSM + Official + Diff visible</span>
        )}
      </div>

      <div className="layer-list">
        {LAYER_CONFIG.map(l => (
          <div className="layer-item" key={l.id}>
            <div className="layer-toggle-row">
              <label className="checkbox-container">
                <input
                  type="checkbox"
                  checked={layers[l.id as keyof LayerState]}
                  onChange={() => toggleLayer(l.id as keyof LayerState)}
                />
                <span className="checkmark" style={{ borderColor: l.color }} />
                <span className="layer-label">{l.label}</span>
              </label>
              {/* Zoom to Layer button (promptui02) */}
              {l.id !== 'osmBase' && (
                <button
                  className="zoom-to-layer-btn"
                  onClick={() => zoomToLayerExtent(l.id)}
                  title={`Zoom to ${l.label}`}
                >
                  🔎
                </button>
              )}
            </div>

            {/* Color swatch */}
            <div className="layer-meta-row">
              <span className="color-swatch" style={{ backgroundColor: l.color }} />
              <span className="layer-color-label">{l.color}</span>
            </div>

            {/* Opacity slider */}
            <div className="opacity-slider-row">
              <span className="opacity-text">
                Opacity: {Math.round(opacities[l.id as keyof OpacityState] * 100)}%
              </span>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={opacities[l.id as keyof OpacityState]}
                onChange={e => changeOpacity(l.id as keyof OpacityState, parseFloat(e.target.value))}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
