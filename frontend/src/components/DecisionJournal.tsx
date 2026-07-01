import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { api, type StrategyProfile } from '../api/client'

type Props = {
  strategies: StrategyProfile[]
}

export default function DecisionJournal({ strategies }: Props) {
  const [decisions, setDecisions] = useState<any[]>([])
  const [ticker, setTicker] = useState('AAPL')
  const [action, setAction] = useState('WATCH')
  const [strategy, setStrategy] = useState('balanced')
  const [quantity, setQuantity] = useState<number | ''>('')
  const [conviction, setConviction] = useState(3)
  const [thesis, setThesis] = useState('')
  const [risks, setRisks] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const strategyOptions = useMemo(() => strategies.map((item) => item.name), [strategies])

  const load = async () => {
    const rows = await api.decisions()
    setDecisions(rows)
  }

  useEffect(() => {
    void load()
  }, [])

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setLoading(true)
    setMessage(null)
    try {
      const payload = await api.createDecision(ticker, {
        action,
        strategy_name: strategy,
        quantity: quantity === '' ? null : quantity,
        conviction,
        thesis,
        risks
      })
      setMessage((payload.warnings || []).join(' | ') || 'Decision saved.')
      await load()
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <h2>Decision journal</h2>
          <p className="muted">Record human decisions alongside the engine snapshot.</p>
        </div>
      </div>

      <form className="journal-form" onSubmit={(event) => void submit(event)}>
        <input value={ticker} onChange={(event) => setTicker(event.target.value.toUpperCase())} placeholder="Ticker" />
        <select value={action} onChange={(event) => setAction(event.target.value)}>
          {['WATCH', 'BUY', 'SELL', 'HOLD', 'AVOID'].map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
        <select value={strategy} onChange={(event) => setStrategy(event.target.value)}>
          {strategyOptions.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
        <input type="number" value={quantity} onChange={(event) => setQuantity(event.target.value === '' ? '' : Number(event.target.value))} placeholder="Quantity" />
        <input type="number" min={1} max={5} value={conviction} onChange={(event) => setConviction(Number(event.target.value))} placeholder="Conviction" />
        <textarea value={thesis} onChange={(event) => setThesis(event.target.value)} placeholder="Thesis" rows={3} />
        <textarea value={risks} onChange={(event) => setRisks(event.target.value)} placeholder="Risks" rows={3} />
        <button className="button" type="submit" disabled={loading}>
          {loading ? 'Saving...' : 'Save decision'}
        </button>
      </form>

      {message ? <div className="status-row">{message}</div> : null}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Ticker</th>
              <th>Action</th>
              <th>Strategy</th>
              <th>Engine rec</th>
              <th>Oppty</th>
              <th>Risk</th>
              <th>Conviction</th>
              <th>Thesis</th>
            </tr>
          </thead>
          <tbody>
            {decisions.map((row) => (
              <tr key={row.id}>
                <td>{row.decision_date}</td>
                <td>{row.ticker}</td>
                <td>{row.action}</td>
                <td>{row.strategy_name}</td>
                <td>{row.engine_recommendation}</td>
                <td>{Number(row.engine_opportunity_score).toFixed(1)}</td>
                <td>{row.engine_risk_category}</td>
                <td>{row.conviction}</td>
                <td>{row.thesis}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
