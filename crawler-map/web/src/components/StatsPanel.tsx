import { useMemo, useCallback } from 'react'
import { PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { useMapContext } from '../context/MapContext'

const COLORS = {
  matched: '#94a3b8', // Slate (neutral)
  changed: '#f97316', // Orange (Modified / Edit)
  missing: '#22c55e', // Green (Add)
  new: '#ef4444',     // Red (Delete)
}

export default function StatsPanel() {
  const { stats, compareResults, isLoading, setHighlightedId, map } = useMapContext()

  // ── Compute extended stats from compareResults ──
  const extendedStats = useMemo(() => {
    if (!compareResults.length) return null

    const avgOverlap = compareResults.reduce((s, r) => s + (r.overlap_ratio || 0), 0) / compareResults.length
    const avgHausdorff = compareResults.reduce((s, r) => s + (r.hausdorff || 0), 0) / compareResults.length

    // Top differences (sorted by lowest overlap)
    const topDiff = [...compareResults]
      .filter(r => r.overlap_ratio < 0.95)
      .sort((a, b) => a.overlap_ratio - b.overlap_ratio)
      .slice(0, 10)

    // Hausdorff histogram buckets
    const hausBuckets = [
      { range: '0-50', count: 0 },
      { range: '50-200', count: 0 },
      { range: '200-500', count: 0 },
      { range: '500-1000', count: 0 },
      { range: '1000+', count: 0 },
    ]
    compareResults.forEach(r => {
      const h = r.hausdorff || 0
      if (h < 50) hausBuckets[0].count++
      else if (h < 200) hausBuckets[1].count++
      else if (h < 500) hausBuckets[2].count++
      else if (h < 1000) hausBuckets[3].count++
      else hausBuckets[4].count++
    })

    // Area diff distribution
    const areaBuckets = [
      { range: '<0.01', count: 0 },
      { range: '0.01-0.1', count: 0 },
      { range: '0.1-1', count: 0 },
      { range: '1-10', count: 0 },
      { range: '10+', count: 0 },
    ]
    compareResults.forEach(r => {
      const a = (r.area_difference_sqm || 0) / 1e6 // km²
      if (a < 0.01) areaBuckets[0].count++
      else if (a < 0.1) areaBuckets[1].count++
      else if (a < 1) areaBuckets[2].count++
      else if (a < 10) areaBuckets[3].count++
      else areaBuckets[4].count++
    })

    return { avgOverlap, avgHausdorff, topDiff, hausBuckets, areaBuckets }
  }, [compareResults])

  // Pie chart data
  const pieData = useMemo(() => {
    if (!stats?.Summary) return []
    return [
      { name: 'Matched', value: stats.Summary.PerfectMatch || 0, color: COLORS.matched },
      { name: 'Changed', value: stats.Summary.Changed || 0, color: COLORS.changed },
      { name: 'Missing', value: stats.Summary.MissingInOSM || 0, color: COLORS.missing },
      { name: 'New', value: stats.Summary.NewInOSM || 0, color: COLORS.new },
    ]
  }, [stats])

  const handleTopDiffClick = useCallback((item: any) => {
    setHighlightedId(item.official_id)
    // Simple toast/notification
  }, [setHighlightedId])

  if (isLoading) {
    return (
      <div className="sidebar-section stats-section">
        <h3>📊 Statistics</h3>
        <div className="loading-spinner-inline">
          <div className="spinner" />
          <span>Loading data...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="sidebar-section stats-section">
      <h3>📊 Statistics Summary</h3>

      {stats?.Summary ? (
        <>
          {/* Summary cards (promptui04, promptui10) */}
          <div className="stats-cards">
            <div className="stat-card matched">
              <span className="stat-card-value">{stats.Summary.PerfectMatch || 0}</span>
              <span className="stat-card-label">Matched</span>
            </div>
            <div className="stat-card changed">
              <span className="stat-card-value">{stats.Summary.Changed || 0}</span>
              <span className="stat-card-label">Changed</span>
            </div>
            <div className="stat-card missing">
              <span className="stat-card-value">{stats.Summary.MissingInOSM || 0}</span>
              <span className="stat-card-label">Missing</span>
            </div>
            <div className="stat-card new">
              <span className="stat-card-value">{stats.Summary.NewInOSM || 0}</span>
              <span className="stat-card-label">New</span>
            </div>
          </div>

          {/* Extended stats from compare results */}
          {extendedStats && (
            <div className="stats-grid">
              <div className="stats-item">
                <span className="stats-name">Total Official:</span>
                <span className="stats-val">{stats.Summary.Total_Official || 0}</span>
              </div>
              <div className="stats-item">
                <span className="stats-name">Avg Overlap:</span>
                <span className="stats-val">{(extendedStats.avgOverlap * 100).toFixed(1)}%</span>
              </div>
              <div className="stats-item">
                <span className="stats-name">Avg Hausdorff:</span>
                <span className="stats-val">{extendedStats.avgHausdorff.toFixed(0)}m</span>
              </div>
            </div>
          )}

          {/* Pie Chart (promptui10) */}
          <div className="chart-container">
            <h4>Status Distribution</h4>
            <ResponsiveContainer width="100%" height={180}>
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={40}
                  outerRadius={70}
                  paddingAngle={3}
                  dataKey="value"
                >
                  {pieData.map((entry, i) => (
                    <Cell key={i} fill={entry.color} stroke="transparent" />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ background: '#1e293b', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, color: '#f8fafc' }}
                />
              </PieChart>
            </ResponsiveContainer>
            <div className="chart-legend">
              {pieData.map(d => (
                <span key={d.name} className="legend-item">
                  <span className="legend-dot" style={{ backgroundColor: d.color }} />
                  {d.name}: {d.value}
                </span>
              ))}
            </div>
          </div>

          {/* Hausdorff Histogram (promptui10) */}
          {extendedStats && (
            <div className="chart-container">
              <h4>Hausdorff Distance (m)</h4>
              <ResponsiveContainer width="100%" height={150}>
                <BarChart data={extendedStats.hausBuckets}>
                  <XAxis dataKey="range" tick={{ fill: '#94a3b8', fontSize: 10 }} />
                  <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} />
                  <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, color: '#f8fafc' }} />
                  <Bar dataKey="count" fill="#38bdf8" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Area Difference Distribution (promptui10) */}
          {extendedStats && (
            <div className="chart-container">
              <h4>Area Difference (km²)</h4>
              <ResponsiveContainer width="100%" height={150}>
                <BarChart data={extendedStats.areaBuckets}>
                  <XAxis dataKey="range" tick={{ fill: '#94a3b8', fontSize: 10 }} />
                  <YAxis tick={{ fill: '#94a3b8', fontSize: 10 }} />
                  <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, color: '#f8fafc' }} />
                  <Bar dataKey="count" fill="#f97316" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Top Difference list (promptui04) */}
          {extendedStats && extendedStats.topDiff.length > 0 && (
            <div className="top-diff-section">
              <h4>⚠️ Top Differences (Overlap &lt; 95%)</h4>
              <div className="top-diff-list">
                {extendedStats.topDiff.map((item, i) => (
                  <div
                    key={i}
                    className="top-diff-item"
                    onClick={() => handleTopDiffClick(item)}
                    title="Click to highlight on map"
                  >
                    <span className="top-diff-name">{item.official_name}</span>
                    <span className="top-diff-val">{(item.overlap_ratio * 100).toFixed(1)}%</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      ) : (
        <p className="loading-text">Run pipeline.py and start API backend to load stats...</p>
      )}
    </div>
  )
}
