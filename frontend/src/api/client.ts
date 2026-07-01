export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

type QueryValue = string | number | boolean | null | undefined

function buildUrl(path: string, params?: Record<string, QueryValue>) {
  const url = new URL(path, API_BASE_URL)
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value === null || value === undefined || value === '') {
        continue
      }
      url.searchParams.set(key, String(value))
    }
  }
  return url.toString()
}

async function requestJson<T>(path: string, init?: RequestInit, params?: Record<string, QueryValue>): Promise<T> {
  const response = await fetch(buildUrl(path, params), {
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {})
    },
    ...init
  })
  const text = await response.text()
  if (!response.ok) {
    throw new Error(text || response.statusText)
  }
  return text ? (JSON.parse(text) as T) : (undefined as T)
}

export type HealthDetails = {
  status: string
  service: string
  database_reachable: boolean
  active_provider: string
  default_scoring_strategy: string
  scoring_model_version: string
  signal_model_version: string
}

export type StrategyProfile = {
  name: string
  description: string
  category_weights: Record<string, number>
  signal_weight_overrides?: Record<string, number>
}

export const api = {
  healthDetails: () => requestJson<HealthDetails>('/health/details'),
  strategies: () => requestJson<StrategyProfile[]>('/strategies'),
  watchlistStatus: () => requestJson<any[]>('/watchlist/status'),
  refreshWatchlist: (params: { strategies?: string; force_reingest?: boolean; generate_signals?: boolean; score?: boolean }) =>
    requestJson<any>('/watchlist/refresh', { method: 'POST' }, params),
  rankings: (params: { strategies?: string; limit?: number; include_signals?: boolean }) =>
    requestJson<Record<string, unknown>>('/rankings/strategies', undefined, params),
  analysis: (ticker: string, compact = true, strategy?: string) =>
    requestJson<any>(`/analysis/${encodeURIComponent(ticker)}`, undefined, { compact, strategy }),
  compareStrategies: (ticker: string, strategies?: string) =>
    requestJson<any[]>(`/analysis/${encodeURIComponent(ticker)}/compare-strategies`, undefined, { strategies }),
  decisions: () => requestJson<any[]>('/decisions'),
  createDecision: (
    ticker: string,
    payload: {
      action: string
      strategy_name?: string
      quantity?: number | null
      conviction: number
      thesis: string
      risks: string
    }
  ) => requestJson<any>(`/decisions/${encodeURIComponent(ticker)}`, { method: 'POST', body: JSON.stringify(payload) }),
  scoreStrategyEvaluation: (params: {
    horizon?: number
    recommendation?: string
    min_opportunity_score?: number
    risk_category?: string
  }) => requestJson<any>('/scores/evaluation/strategies', undefined, params),
  decisionEvaluation: (params: { horizon?: number; strategy_name?: string; min_conviction?: number }) =>
    requestJson<any>('/decisions/evaluation', undefined, params)
}
