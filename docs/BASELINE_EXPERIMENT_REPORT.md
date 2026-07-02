# Baseline Experiment Report

Date: 2026-07-01

## 1. Data coverage

- Watchlist tickers tested: AAPL, AMZN, BRK.B, COST, GOOGL, JNJ, KO, META, MSFT, NVDA, PEP, PLTR, RIVN, SOFI, SPY, TSLA, V
- Price rows: 12,784 across 17 tickers, about 752 rows per ticker on average.
- Fundamentals rows: 17 across 17 tickers.
- Score rows: 1,887 across 17 tickers.
- Signal rows: 7,548 total.
- Benchmark availability: SPY is present in the local cache and was available for all experiment horizons.
- Watchlist tickers missing fundamentals in the local cache: none
- Watchlist tickers missing prices in the local cache: none

### Strategy-level score distributions

- balanced: opportunity score mean 48.73, median 49.69, p10 38.68, p90 56.98
  - recommendations: `{'AVOID': 69, 'HOLD': 477, 'SPECULATIVE': 81, 'WATCH': 2}`
  - risk categories: `{'HIGH_RISK': 177, 'MEDIUM_RISK': 298, 'SPECULATIVE': 90, 'STABLE': 64}`
- conservative_quality: opportunity score mean 48.89, median 50.39, p10 36.01, p90 59.23
  - recommendations: `{'AVOID': 30, 'HOLD': 402, 'SPECULATIVE': 151, 'WATCH': 46}`
  - risk categories: `{'HIGH_RISK': 142, 'MEDIUM_RISK': 274, 'SPECULATIVE': 174, 'STABLE': 39}`
- value_recovery: opportunity score mean 54.00, median 54.36, p10 44.75, p90 62.08
  - recommendations: `{'AVOID': 7, 'HOLD': 440, 'SPECULATIVE': 58, 'WATCH': 124}`
  - risk categories: `{'HIGH_RISK': 177, 'MEDIUM_RISK': 298, 'SPECULATIVE': 90, 'STABLE': 64}`

## 2. Experiment coverage

- Total experiments run: 408
- Total experiment result rows: 59,060
- Experiments with zero usable observations: 148
- Experiments with fewer than 20 usable observations: 168

| Experiment type | Count | Zero-observation | Under-20 observations |
| --- | ---: | ---: | ---: |
| strategy_score_threshold | 36 | 2 | 4 |
| recommendation_outcome | 48 | 2 | 8 |
| risk_category_outcome | 36 | 0 | 0 |
| signal_threshold | 288 | 144 | 156 |

## 3. Top results by average excess return

| Experiment | Type | Strategy | Horizon | Obs | Avg excess % | Median excess % | Win rate | Outcome split |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| balanced_high_risk_365d | risk_category_outcome | balanced | 365 | 101 | 70.14 | 31.32 | 0.74 | O:75 N:4 U:22 |
| value_recovery_high_risk_365d | risk_category_outcome | value_recovery | 365 | 101 | 70.14 | 31.32 | 0.74 | O:75 N:4 U:22 |
| conservative_quality_speculative_365d | risk_category_outcome | conservative_quality | 365 | 109 | 66.50 | 29.48 | 0.76 | O:82 N:4 U:23 |
| balanced_avoid_365d | recommendation_outcome | balanced | 365 | 47 | 52.65 | 14.52 | 0.60 | O:28 N:2 U:17 |
| conservative_quality_speculative_365d | recommendation_outcome | conservative_quality | 365 | 90 | 51.26 | 21.21 | 0.70 | O:62 N:4 U:24 |

## 4. Worst results by average excess return

| Experiment | Type | Strategy | Horizon | Obs | Avg excess % | Median excess % | Win rate | Outcome split |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| conservative_quality_medium_risk_365d | risk_category_outcome | conservative_quality | 365 | 175 | -7.78 | -8.04 | 0.30 | O:37 N:34 U:104 |
| conservative_quality_opportunity_ge_60_365d | strategy_score_threshold | conservative_quality | 365 | 35 | -4.96 | -2.39 | 0.46 | O:7 N:11 U:17 |
| conservative_quality_watch_365d | recommendation_outcome | conservative_quality | 365 | 35 | -4.96 | -2.39 | 0.46 | O:7 N:11 U:17 |
| conservative_quality_opportunity_ge_50_365d | strategy_score_threshold | conservative_quality | 365 | 223 | -4.87 | -4.04 | 0.40 | O:50 N:63 U:110 |
| conservative_quality_medium_risk_180d | risk_category_outcome | conservative_quality | 180 | 223 | -3.64 | -4.78 | 0.39 | O:60 N:53 U:110 |

## 5. Inconclusive results

- The matrix still contains 148 zero-observation experiments and 168 experiments with fewer than 20 usable observations.
- Signal-threshold experiments are the sparsest part of the matrix, especially for fundamental signals at 60/70 thresholds.
- WATCH is still sparse in the current score history, which makes it hard to test directly.
- Thresholds that yield zero observations should be treated as inconclusive rather than negative.

## 6. Signal usefulness

| Signal | Experiments | Avail total | Nonzero exps | Avg excess % | Best % | Worst % | Verdict | Note |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| debt_to_equity | 24 | 0 | 0 | n/a | n/a | n/a | INCONCLUSIVE | No observations at current thresholds. |
| free_cash_flow_positive | 24 | 0 | 0 | n/a | n/a | n/a | INCONCLUSIVE | No observations at current thresholds. |
| ma_50_vs_200 | 24 | 3,720 | 24 | 13.34 | 48.35 | 0.82 | KEEP | Positive excess return and enough observations to matter. |
| max_drawdown | 24 | 9,486 | 24 | 3.75 | 17.68 | 0.08 | KEEP | Positive excess return and enough observations to matter. |
| pe_ratio | 24 | 0 | 0 | n/a | n/a | n/a | INCONCLUSIVE | No observations at current thresholds. |
| price_to_sales | 24 | 0 | 0 | n/a | n/a | n/a | INCONCLUSIVE | No observations at current thresholds. |
| return_12m | 24 | 2,898 | 24 | 11.47 | 33.14 | 1.33 | KEEP | Positive excess return and enough observations to matter. |
| return_3m | 24 | 4,314 | 24 | 13.24 | 40.11 | 1.02 | KEEP | Positive excess return and enough observations to matter. |
| return_6m | 24 | 4,479 | 24 | 10.94 | 35.58 | 1.08 | KEEP | Positive excess return and enough observations to matter. |
| revenue_growth_consistency | 24 | 0 | 0 | n/a | n/a | n/a | INCONCLUSIVE | No observations at current thresholds. |
| roe | 24 | 0 | 0 | n/a | n/a | n/a | INCONCLUSIVE | No observations at current thresholds. |
| volatility | 24 | 1,578 | 24 | -0.54 | 0.33 | -1.60 | IMPROVE | Observed, but weak or negative excess return. |

Interpretation:

- Price-derived signals are the useful part of the current system. `return_3m`, `return_6m`, `return_12m`, `ma_50_vs_200`, and `max_drawdown` all produced enough historical observations to test.
- `volatility` is usable but weaker; its average excess return is slightly negative at the tested thresholds.
- Fundamental threshold experiments are mostly inconclusive at 60/70 because the current normalization and historical snapshot coverage rarely push those signals that high.
- `free_cash_flow_positive` exists in the diagnostics and the signal layer, but the current threshold matrix did not produce enough historical hits to support a stronger claim.

## 7. Strategy usefulness

| Strategy | Threshold exps | Avg excess % | Avg win rate | 365d threshold snapshot (threshold@obs:avg excess) |
| --- | ---: | ---: | ---: | --- |
| balanced | 12 | 2.97 | 0.51 | 40@362:17.89, 50@205:11.49, 60@0:n/a |
| conservative_quality | 12 | 0.20 | 0.50 | 40@340:14.20, 50@223:-4.87, 60@35:-4.96 |
| value_recovery | 12 | 5.59 | 0.51 | 40@399:19.40, 50@316:12.63, 60@79:11.50 |

Interpretation:

- `value_recovery` looks the most promising on the current baseline. It has the highest opportunity-score distribution and the strongest long-horizon thresholded results.
- `balanced` is next best on long horizons but does not separate as strongly as `value_recovery`.
- `conservative_quality` is stable at low thresholds, but its higher-threshold long-horizon results weaken or turn negative.
- The strategy profiles do differentiate the score distribution and the thresholded outcomes, which means the strategy layer is doing real work.

## 8. Warnings

- The universe is small: 17 watchlist names plus SPY.
- yfinance fundamentals are partial and should not be treated as durable institutional-quality data.
- The dataset still carries survivorship bias because it only covers the names currently in the watchlist.
- Monthly score snapshots are better than a single current-day score, but the sample is still small for some conditions.
- No conclusion here should be treated as final. This is a baseline check, not proof of a profitable strategy.

## 9. Bottom line

The experiment engine is working. The signal layer now produces enough variation to run meaningful baseline tests, but only a subset of signals currently have enough historical support to trust. Price-derived signals and the `value_recovery` strategy are the clearest current candidates for further research.
