import React, { useState, useEffect } from 'react'
import axios from 'axios'
import './App.css'

function App() {
  const [shares, setShares] = useState([])
  const [assets, setAssets] = useState([])
  const [incentive, setIncentive] = useState(null)
  const [priceForecast, setPriceForecast] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    // Fetch initial data
    const fetchData = async () => {
      try {
        setLoading(true)

        // Fetch assets
        const assetsResponse = await axios.get('/api/v1/assets')
        setAssets(assetsResponse.data.assets || [])

        // Fetch latest shares
        const sharesResponse = await axios.get('/api/shares/latest')
        setShares(sharesResponse.data || [])

        // Fetch price forecast (weather + METOC nowcast driven). Optional service.
        try {
          const pf = await axios.get('/api/v1/price/forecast')
          setPriceForecast(pf.data || null)
        } catch {
          setPriceForecast(null)
        }

        setError(null)
      } catch (err) {
        console.error('Error fetching data:', err)
        setError('Failed to load dashboard data')
      } finally {
        setLoading(false)
      }
    }

    fetchData()
    const interval = setInterval(fetchData, 30000) // Refresh every 30s

    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    // WebSocket connection for real-time incentive updates
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws`)

    ws.onopen = () => {
      console.log('WebSocket connected')
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        setIncentive(data)
      } catch (err) {
        console.error('Error parsing WebSocket message:', err)
      }
    }

    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
    }

    ws.onclose = () => {
      console.log('WebSocket disconnected')
    }

    return () => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.close()
      }
    }
  }, [])

  const calculateStats = () => {
    const totalKwh = shares.reduce((sum, share) => sum + (share.kwh || 0), 0)
    const totalValue = shares.reduce((sum, share) => sum + (share.price * share.kwh || 0), 0)
    return { totalKwh, totalValue }
  }

  const { totalKwh, totalValue } = calculateStats()

  return (
    <div className="container">
      <div className="header">
        <h1>⚡ ECO-VPP Dashboard</h1>
        <p>Energy Community Orchestrated - Virtual Power Plant Control Center</p>
      </div>

      {error && <div className="error">⚠️ {error}</div>}

      <div className="grid">
        {/* Flexibility Incentive Card */}
        {incentive && (
          <div className="card">
            <h2>💰 Flexibility Incentive</h2>
            <div className="value">€{incentive.price?.toFixed(2) || 'N/A'}/kWh</div>
            <p><strong>Grid Signal:</strong> {(incentive.signal * 100).toFixed(0)}% curtailment</p>
            <p className="status active">
              Load Limit: {(100 - incentive.signal * 100).toFixed(0)}%
            </p>
          </div>
        )}

        {/* Price Forecast Card (weather + METOC nowcast) */}
        {priceForecast && priceForecast.points && priceForecast.points.length > 0 && (() => {
          const pts = priceForecast.points
          const now = Date.now()
          const next = pts.reduce((a, b) =>
            Math.abs(new Date(b.timestamp).getTime() - now) < Math.abs(new Date(a.timestamp).getTime() - now) ? b : a)
          const prices = pts.map((p) => p.price_eur_mwh)
          const lo = Math.min(...prices), hi = Math.max(...prices)
          return (
            <div className="card">
              <h2>🌤️ Price Forecast</h2>
              <div className="value">€{next.price_eur_mwh.toFixed(0)}<small>/MWh</small></div>
              <p><strong>Next {priceForecast.resolution_min}-min step</strong> · range €{lo.toFixed(0)}–{hi.toFixed(0)}/MWh</p>
              <p className="status active">Source: {priceForecast.provider} · {pts.length} pts</p>
              <div style={{ display: 'flex', alignItems: 'flex-end', gap: 2, height: 44, marginTop: 8 }}>
                {pts.slice(0, 36).map((p, i) => {
                  const h = hi > lo ? 8 + ((p.price_eur_mwh - lo) / (hi - lo)) * 92 : 50
                  return <div key={i} title={`€${p.price_eur_mwh}/MWh`}
                    style={{ flex: 1, height: `${h}%`, background: '#667eea', borderRadius: '2px 2px 0 0', opacity: 0.85 }} />
                })}
              </div>
            </div>
          )
        })()}

        {/* Energy Stats Card */}
        <div className="card">
          <h2>📊 Energy Statistics (24h)</h2>
          <div className="value">{totalKwh.toFixed(2)} kWh</div>
          <p><strong>Total Value:</strong> €{totalValue.toFixed(2)}</p>
          <p><strong>Average Price:</strong> €{(totalValue / totalKwh || 0).toFixed(3)}/kWh</p>
        </div>

        {/* Registered Assets Card */}
        <div className="card">
          <h2>🏠 Registered Assets</h2>
          <div className="value">{assets.length}</div>
          <p><strong>Device Types:</strong></p>
          <div>
            {assets.map((asset) => (
              <div key={asset.id} className="badge" style={{ marginRight: '0.5rem', marginTop: '0.25rem' }}>
                {asset.asset_type}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Latest Energy Shares */}
      <div className="card">
        <h2>📈 Latest Energy Shares</h2>
        {loading ? (
          <div className="loading">Loading shares...</div>
        ) : shares.length === 0 ? (
          <div className="loading">No energy shares recorded yet</div>
        ) : (
          <div>
            {shares.slice(0, 10).map((share, index) => (
              <div key={index} className="list-item">
                <div>
                  <strong>{share.asset}</strong>
                  <br />
                  <small>{new Date(share.time).toLocaleString()}</small>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div><strong>{share.kwh.toFixed(2)} kWh</strong></div>
                  <div style={{ color: '#667eea', fontWeight: 'bold' }}>
                    €{(share.price * share.kwh).toFixed(2)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Assets List */}
      {assets.length > 0 && (
        <div className="card" style={{ marginTop: '1.5rem' }}>
          <h2>🔧 Connected Assets</h2>
          <div>
            {assets.map((asset) => (
              <div key={asset.id} className="list-item">
                <div>
                  <strong>{asset.did}</strong>
                  <br />
                  <small>{asset.location || 'No location set'}</small>
                </div>
                <div>
                  <span className="badge">{asset.asset_type}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default App
