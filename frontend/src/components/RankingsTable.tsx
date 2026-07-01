import { useEffect, useMemo, useState } from 'react'
import { api, type StrategyProfile } from '../api/client'

type Props = {
  strategies: StrategyProfile[]
}

type RankingRow = {
  rank: number
  ticker: string
  recommendation: string
  risk_category: string
  opportunity_score: number
  quality_score: number
  valuation_score: number
  momentum_score: number
  risk_score: number
  summary: string
  positive_signals?: any[]
  negative_signals?: any[]
}

export default function RankingsTable({ strategies }: Props) {
  const [strategy, setStrategy] = useState('balanced')
  const [limit, setLimit] = useState(10)
  const [includeSignals, setIncludeSignals] = useState(false)
  const [rows, setRows] = useState<RankingRow[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const strategyOptions = useMemo(() => strategies.map((item) => item.name), [strategies])

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await api.rankings({
        strategies: strategy,
        limit,
        include_signals: includeSignals
      })
      const data = response.rankings as Record<string, RankingRow[]>
      setRows(data[strategy] || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
  }, [])

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <h2>Rankings</h2>
          <p className="muted">Watchlist ranking for one strategy at a time.</p>
        </div>
        <div className="controls">
          <select value={strategy} onChange={(event) => setStrategy(event.target.value)}>
            {strategyOptions.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          <input
            type="number"
            min={1}
            max={100}
            value={limit}
            onChange={(event) => setLimit(Number(event.target.value))}
          />
          <label className="checkbox">
            <input type="checkbox" checked={includeSignals} onChange={(event) => setIncludeSignals(event.target.checked)} />
            Include signals
          </label>
          <button className="button" onClick={() => void load()} disabled={loading}>
            {loading ? 'Loading...' : 'Load'}
          </button>
        </div>
      </div>

      {error ? <div className="error-box">{error}</div> : null}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Rank</th>
              <th>Ticker</th>
              <th>Recommendation</th>
              <th>Risk</th>
              <th>Opportunity</th>
              <th>Quality</th>
              <th>Valuation</th>
              <th>Momentum</th>
              <th>Risk score</th>
              <th>Summary</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.ticker}>
                <td>{row.rank}</td>
                <td>{row.ticker}</td>
                <td>{row.recommendation}</td>
                <td>{row.risk_category}</td>
                <td>{row.opportunity_score.toFixed(1)}</td>
                <td>{row.quality_score.toFixed(1)}</td>
                <td>{row.valuation_score.toFixed(1)}</td>
                <td>{row.momentum_score.toFixed(1)}</td>
                <td>{row.risk_score.toFixed(1)}</td>
                <td>
                  <div className="stack">
                    <span>{row.summary}</span>
                    {includeSignals ? (
                      <>
                        <span className="muted">Positive: {(row.positive_signals || []).slice(0, 3).map((signal) => signal.signal_name).join(', ') || 'n/a'}</span>
                        <span className="muted">Negative: {(row.negative_signals || []).slice(0, 3).map((signal) => signal.signal_name).join(', ') || 'n/a'}</span>
                      </>
                    ) : null}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
