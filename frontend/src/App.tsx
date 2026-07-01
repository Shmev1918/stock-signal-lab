import { useCallback, useEffect, useMemo, useState } from 'react'
import Layout from './components/Layout'
import WatchlistStatus from './components/WatchlistStatus'
import RankingsTable from './components/RankingsTable'
import StockAnalysis from './components/StockAnalysis'
import DecisionJournal from './components/DecisionJournal'
import EvaluationSummary from './components/EvaluationSummary'
import { api, type HealthDetails, type StrategyProfile } from './api/client'

function formatWarning(dateValue: string | null | undefined, ticker: string) {
  if (!dateValue) {
    return `${ticker}: latest price data missing`
  }
  const ageMs = Date.now() - new Date(dateValue).getTime()
  if (ageMs > 7 * 24 * 60 * 60 * 1000) {
    return `${ticker}: latest price data is stale`
  }
  return null
}

export default function App() {
  const [health, setHealth] = useState<HealthDetails | null>(null)
  const [strategies, setStrategies] = useState<StrategyProfile[]>([])
  const [watchlistStatus, setWatchlistStatus] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshNonce, setRefreshNonce] = useState(0)

  useEffect(() => {
    void Promise.all([api.healthDetails(), api.strategies(), api.watchlistStatus()])
      .then(([healthResult, strategiesResult, statusResult]) => {
        setHealth(healthResult)
        setStrategies(strategiesResult)
        setWatchlistStatus(statusResult)
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : String(err))
      })
      .finally(() => setLoading(false))
  }, [refreshNonce])

  const staleWarnings = useMemo(
    () => watchlistStatus.map((row) => formatWarning(row.latest_price_date, row.ticker)).filter((value): value is string => Boolean(value)),
    [watchlistStatus]
  )

  const refreshWatchlist = useCallback(async () => {
    const result = await api.refreshWatchlist({
      strategies: 'balanced,conservative_quality,value_recovery'
    })
    setRefreshNonce((value) => value + 1)
    return result
  }, [])

  if (loading) {
    return (
      <Layout title="stock-signal-lab" subtitle="Loading local cockpit...">
        <div className="panel">Loading...</div>
      </Layout>
    )
  }

  return (
    <Layout title="stock-signal-lab" subtitle="Local stock observability and decision lab">
      {error ? <div className="error-box">{error}</div> : null}

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>Health</h2>
            <p className="muted">Provider and model snapshot.</p>
          </div>
        </div>
        {health ? (
          <div className="health-grid">
            <div className="stat-card">
              <span className="muted">Provider</span>
              <strong>{health.active_provider}</strong>
            </div>
            <div className="stat-card">
              <span className="muted">Default strategy</span>
              <strong>{health.default_scoring_strategy}</strong>
            </div>
            <div className="stat-card">
              <span className="muted">Scoring model</span>
              <strong>{health.scoring_model_version}</strong>
            </div>
            <div className="stat-card">
              <span className="muted">Signal model</span>
              <strong>{health.signal_model_version}</strong>
            </div>
          </div>
        ) : null}

        {staleWarnings.length > 0 ? (
          <div className="warning-box">
            <strong>Stale data warnings</strong>
            <ul>
              {staleWarnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </div>
        ) : (
          <div className="muted">No stale price warnings.</div>
        )}
      </section>

      <WatchlistStatus
        statusRows={watchlistStatus}
        onRefreshWatchlist={refreshWatchlist}
      />
      <RankingsTable strategies={strategies} />
      <StockAnalysis strategies={strategies} />
      <DecisionJournal strategies={strategies} />
      <EvaluationSummary />
    </Layout>
  )
}
