# Feature Registry

This document is generated from `app/signals/registry.py`.
Do not edit the table content by hand; regenerate it from metadata instead.

Last generated: 2026-07-01

The registry is the canonical reference for signal metadata in analytics work.

## MOMENTUM

| Name | Provider | Source Fields | Normalization Formula | Expected Range | Current Variation | Experiment Status | Predictive Status | Confidence | Known Limitations | Last Validated |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| return_3m | internal | daily_prices.close, daily_prices.price_date | normalized_score = linear_score(3m return, -0.30, 0.30, higher_is_better=True) | raw return roughly -100%..+100%; normalized score 0-100 | Varies on real price histories and is usually one of the most informative signals. | baseline-tested | inconclusive | MEDIUM | Requires enough lookback rows and can be noisy for thin histories. | 2026-07-01 |
| return_6m | internal | daily_prices.close, daily_prices.price_date | normalized_score = linear_score(6m return, -0.40, 0.40, higher_is_better=True) | raw return roughly -100%..+100%; normalized score 0-100 | Varies across live data and tends to be smoother than 3m momentum. | baseline-tested | inconclusive | MEDIUM | Depends on having enough trading days before the as-of date. | 2026-07-01 |
| return_12m | internal | daily_prices.close, daily_prices.price_date | normalized_score = linear_score(12m return, -0.60, 0.80, higher_is_better=True) | raw return roughly -100%..+100%; normalized score 0-100 | Varies on longer histories and captures broader trend persistence. | baseline-tested | inconclusive | MEDIUM | Long lookback windows can exclude newer listings or sparse histories. | 2026-07-01 |
| ma_50_vs_200 | internal | daily_prices.close, daily_prices.price_date | normalized_score = linear_score((ma50 / ma200) - 1, -0.25, 0.25, higher_is_better=True) | raw relative spread roughly -25%..+25% in normal conditions; normalized score 0-100 | Varies when at least 200 price rows exist; otherwise it falls back or stays neutral. | baseline-tested | inconclusive | MEDIUM | Requires long enough price history to calculate both moving averages. | 2026-07-01 |

## QUALITY

| Name | Provider | Source Fields | Normalization Formula | Expected Range | Current Variation | Experiment Status | Predictive Status | Confidence | Known Limitations | Last Validated |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| revenue_growth_consistency | internal | fundamentals.as_of_date, fundamentals.revenue_growth | normalized_score = linear transform of revenue growth consistency over available fundamentals | raw consistency roughly 0-1; normalized score 0-100 | Varies when multiple fundamental snapshots exist; can flatten when fundamentals are sparse. | baseline-tested | inconclusive | LOW | yfinance fundamentals are often partial, so historical consistency can be thin. | 2026-07-01 |
| roe | internal | fundamentals.as_of_date, fundamentals.return_on_equity | normalized_score = linear_score(return_on_equity, -0.10, 0.40, higher_is_better=True) | raw ROE typically negative to strongly positive; normalized score 0-100 | Varies when return_on_equity is available; otherwise falls back toward neutral. | baseline-tested | inconclusive | LOW | Coverage is limited by provider fundamentals availability and stale snapshots. | 2026-07-01 |
| debt_to_equity | internal | fundamentals.as_of_date, fundamentals.debt_to_equity | normalized_score = linear_score(debt_to_equity, 0.0, 4.0, higher_is_better=False) | raw debt/equity >= 0; normalized score 0-100 | Varies when debt_to_equity is reported; can be missing for some issuers. | baseline-tested | inconclusive | LOW | Fundamental debt ratios may be missing or inconsistent across providers. | 2026-07-01 |
| free_cash_flow_positive | internal | fundamentals.as_of_date, fundamentals.free_cash_flow | normalized_score = 100 if free_cash_flow > 0 else 0; missing data should be explicit | raw free cash flow can be negative or positive; normalized score 0-100 | Varies only when free_cash_flow is populated; otherwise the signal can be missing-data limited. | baseline-tested | inconclusive | LOW | Positive/negative classification is only as good as the provider's free cash flow coverage. | 2026-07-01 |

## RISK

| Name | Provider | Source Fields | Normalization Formula | Expected Range | Current Variation | Experiment Status | Predictive Status | Confidence | Known Limitations | Last Validated |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| volatility | internal | daily_prices.close, daily_prices.price_date | normalized_score = clamp(100 - min(annualized_volatility * 250, 100)) | raw annualized volatility >= 0; normalized score 0-100 | Varies across real price histories; sensitive to price churn and series length. | baseline-tested | inconclusive | MEDIUM | Requires enough price rows to estimate stable annualized volatility. | 2026-07-01 |
| max_drawdown | internal | daily_prices.close, daily_prices.price_date | normalized_score = clamp(100 - min(abs(max_drawdown) * 100, 100)) | raw drawdown -100%..0%; normalized score 0-100 | Varies across live price histories and reflects the worst peak-to-trough decline. | baseline-tested | inconclusive | MEDIUM | Needs a meaningful history window; short histories can underestimate drawdown. | 2026-07-01 |

## VALUATION

| Name | Provider | Source Fields | Normalization Formula | Expected Range | Current Variation | Experiment Status | Predictive Status | Confidence | Known Limitations | Last Validated |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| pe_ratio | internal | fundamentals.as_of_date, fundamentals.pe_ratio | normalized_score = linear_score(pe_ratio, 8.0, 45.0, higher_is_better=False) | raw P/E usually positive and unbounded; normalized score 0-100 | Varies where trailing P/E is present; missing values are common for unprofitable names. | baseline-tested | inconclusive | MEDIUM | Unprofitable companies and partial fundamentals can flatten coverage. | 2026-07-01 |
| price_to_sales | internal | fundamentals.as_of_date, fundamentals.price_to_sales | normalized_score = linear_score(price_to_sales, 1.0, 15.0, higher_is_better=False) | raw P/S usually positive and unbounded; normalized score 0-100 | Varies when sales-based valuation is available; typically broader than P/E coverage. | baseline-tested | inconclusive | MEDIUM | Comparability across sectors is limited and provider coverage can be partial. | 2026-07-01 |
