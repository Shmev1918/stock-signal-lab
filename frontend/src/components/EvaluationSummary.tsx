import { useEffect, useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api/client'

const COLORS = ['#4f46e5', '#0f766e', '#b45309', '#7c3aed', '#dc2626']

export default function EvaluationSummary() {
  const [scoreEval, setScoreEval] = useState<any | null>(null)
  const [decisionEval, setDecisionEval] = useState<any | null>(null)

  useEffect(() => {
    void Promise.all([api.scoreStrategyEvaluation({ horizon: 90 }), api.decisionEvaluation({ horizon: 90 })]).then(([scores, decisions]) => {
      setScoreEval(scores)
      setDecisionEval(decisions)
    })
  }, [])

  const chartData = useMemo(() => {
    const strategies = scoreEval?.strategies || {}
    return Object.entries(strategies).map(([name, row]: [string, any]) => ({
      name,
      return: row.average_return ?? 0
    }))
  }, [scoreEval])

  return (
    <section className="panel">
      <div className="panel-header">
        <div>
          <h2>Evaluation</h2>
          <p className="muted">Simple 90-day score and decision summaries.</p>
        </div>
      </div>

      <div className="analysis-grid">
        <div className="analysis-card">
          <h3>Strategy evaluation</h3>
          <div className="chart-box">
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="name" />
                <YAxis />
                <Tooltip />
                <Bar dataKey="return">
                  {chartData.map((entry, index) => (
                    <Cell key={entry.name} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Strategy</th>
                  <th>Count</th>
                  <th>Avg return</th>
                  <th>Win rate</th>
                  <th>Excess vs benchmark</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(scoreEval?.strategies || {}).map(([name, row]: [string, any]) => (
                  <tr key={name}>
                    <td>{name}</td>
                    <td>{row.count}</td>
                    <td>{row.average_return?.toFixed?.(2) ?? 'n/a'}</td>
                    <td>{row.win_rate != null ? `${(row.win_rate * 100).toFixed(1)}%` : 'n/a'}</td>
                    <td>{row.excess_return_vs_benchmark?.toFixed?.(2) ?? 'n/a'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="analysis-card">
          <h3>Decision evaluation</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Group</th>
                  <th>Count</th>
                  <th>Avg return</th>
                  <th>Win rate</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(decisionEval?.groups?.human_action || {}).map(([name, row]: [string, any]) => (
                  <tr key={name}>
                    <td>{name}</td>
                    <td>{row.count}</td>
                    <td>{row.average_return?.toFixed?.(2) ?? 'n/a'}</td>
                    <td>{row.win_rate != null ? `${(row.win_rate * 100).toFixed(1)}%` : 'n/a'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  )
}
