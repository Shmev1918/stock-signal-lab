import { useEffect, useMemo, useState } from 'react'
import { api, type StrategyProfile } from '../api/client'

type Props = {
  strategies: StrategyProfile[]
}

export default function StockAnalysis({ strategies }: Props) {
  const [ticker, setTicker] = useState('AAPL')
  const [strategy, setStrategy] = useState('balanced')
  const [analysis, setAnalysis] = useState<any | null>(null)
  const [comparison, setComparison] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const strategyOptions = useMemo(() => strategies.map((item) => item.name), [strategies])

  const load = async () => {
    setLoading(true)
    setError(null)
    try {
      const [analysisResult, comparisonResult] = await Promise.all([
        api.analysis(ticker, true, strategy),
        api.compareStrategies(ticker)
      ])
      setAnalysis(analysisResult)
      setComparison(comparisonResult)
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
          <h2>Stock analysis</h2>
          <p className="muted">Inspect one ticker and compare strategy interpretations.</p>
        </div>
        <div className="controls">
          <input value={ticker} onChange={(event) => setTicker(event.target.value.toUpperCase())} />
          <select value={strategy} onChange={(event) => setStrategy(event.target.value)}>
            {strategyOptions.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          <button className="button" onClick={() => void load()} disabled={loading}>
            {loading ? 'Loading...' : 'Inspect'}
          </button>
        </div>
      </div>

      {error ? <div className="error-box">{error}</div> : null}

      {analysis ? (
        <div className="analysis-grid">
          <div className="analysis-card">
            <h3>
              {analysis.ticker} {analysis.recommendation} / {analysis.risk_category}
            </h3>
            <div className="muted">
              Strategy: {analysis.strategy_name} | Score as of: {analysis.latest_score?.as_of_date || 'n/a'} | Scored at:{' '}
              {analysis.latest_score?.created_at || 'n/a'}
            </div>
            <div className="score-grid">
              <span>Risk: {analysis.scores.risk.toFixed(1)}</span>
              <span>Quality: {analysis.scores.quality.toFixed(1)}</span>
              <span>Valuation: {analysis.scores.valuation.toFixed(1)}</span>
              <span>Momentum: {analysis.scores.momentum.toFixed(1)}</span>
              <span>Opportunity: {analysis.scores.opportunity.toFixed(1)}</span>
            </div>
            <p>{analysis.summary}</p>
            {analysis.warnings?.length ? (
              <div className="warning-box">
                <strong>Warnings</strong>
                <ul>
                  {analysis.warnings.map((warning: string) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>

          <div className="analysis-card">
            <h3>Positive signals</h3>
            <ul>
              {analysis.positive_signals.map((signal: any) => (
                <li key={signal.signal_name}>
                  {signal.signal_name}: {signal.severity}
                </li>
              ))}
            </ul>
          </div>

          <div className="analysis-card">
            <h3>Negative signals</h3>
            <ul>
              {analysis.negative_signals.map((signal: any) => (
                <li key={signal.signal_name}>
                  {signal.signal_name}: {signal.severity}
                </li>
              ))}
            </ul>
          </div>

          <div className="analysis-card">
            <h3>Strategy comparison</h3>
            <div className="stack">
              {comparison.map((item) => (
                <div key={item.strategy_name} className="comparison-row">
                  <strong>{item.strategy_name}</strong>
                  <span>
                    {item.recommendation} / {item.risk_category} / {item.scores.opportunity.toFixed(1)}
                  </span>
                  <span className="muted">{item.summary}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      ) : null}
    </section>
  )
}
