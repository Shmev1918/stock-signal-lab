import { useMemo, useState } from 'react'

type Props = {
  statusRows: any[]
  onRefreshWatchlist: () => Promise<any>
}

function isStale(dateValue: string | null | undefined) {
  if (!dateValue) {
    return true
  }
  const ageMs = Date.now() - new Date(dateValue).getTime()
  return ageMs > 7 * 24 * 60 * 60 * 1000
}

export default function WatchlistStatus({ statusRows, onRefreshWatchlist }: Props) {
  const [refreshing, setRefreshing] = useState(false)
  const [refreshResult, setRefreshResult] = useState<any | null>(null)

  const staleWarnings = useMemo(() => {
    return statusRows
      .filter((row) => isStale(row.latest_price_date))
      .map((row) => `${row.ticker}: latest price data is stale or missing`)
  }, [statusRows])

  const runRefresh = async () => {
    setRefreshing(true)
    try {
      const result = await onRefreshWatchlist()
      setRefreshResult(result)
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <h2>Dashboard home</h2>
          <p className="muted">Health, provider, model versions, and stale-data warnings.</p>
        </div>
        <button className="button" onClick={() => void runRefresh()} disabled={refreshing}>
          {refreshing ? 'Refreshing...' : 'Refresh watchlist'}
        </button>
      </div>

      {staleWarnings.length > 0 ? (
        <div className="warning-box">
          <strong>Warnings</strong>
          <ul>
            {staleWarnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : (
        <div className="muted">No stale price warnings.</div>
      )}

      {refreshResult ? (
        <div className="status-row">
          <span>Last refresh provider: {refreshResult.provider}</span>
          <span>Processed: {refreshResult.tickers_processed}</span>
          <span>Failures: {refreshResult.failures?.length || 0}</span>
        </div>
      ) : null}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Price</th>
              <th>Signal</th>
              <th>Score</th>
              <th>Strategies</th>
              <th>Sources</th>
            </tr>
          </thead>
          <tbody>
            {statusRows.map((row) => (
              <tr key={row.ticker}>
                <td>{row.ticker}</td>
                <td>{row.latest_price_date || 'n/a'}</td>
                <td>{row.latest_signal_date || 'n/a'}</td>
                <td>{row.latest_score_date || 'n/a'}</td>
                <td>{(row.available_strategies || []).join(', ') || 'n/a'}</td>
                <td>
                  <div className="stack">
                    <span>prices: {row.data_sources?.prices || 'n/a'}</span>
                    <span>fundamentals: {row.data_sources?.fundamentals || 'n/a'}</span>
                    <span>signals: {row.data_sources?.signals || 'n/a'}</span>
                    <span>scores: {row.data_sources?.scores || 'n/a'}</span>
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
