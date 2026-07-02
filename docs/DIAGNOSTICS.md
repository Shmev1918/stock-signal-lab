# Diagnostics

Distribution analysis is how we check whether the engine is producing useful variation or just flat/default outputs.

## Why this matters

If scores are compressed into a narrow band, then:

- thresholds stop selecting anything meaningful
- experiments become sparse or empty
- strategies start looking identical
- the engine cannot separate stronger opportunities from weaker ones

Before tuning the model, we need to know whether the problem is:

- too little variation
- overly pessimistic scoring
- missing data
- weak signal formulas

## What to inspect

Look at these distributions by strategy:

- opportunity_score
- risk_score
- quality_score
- valuation_score
- momentum_score
- recommendations
- risk_categories
- signal normalized scores

## Percentiles

Percentiles help show the shape of the distribution.

- `p10` shows the low tail
- `p50` is the median
- `p90` shows the high tail

When `p10`, `p50`, and `p90` are close together, the model is compressed.

When `p10` is near `0`, `p50` near `50`, and `p90` near `100`, the signal may be behaving like a coarse bucket rather than a graded score.

## What bad compression looks like

Common failure modes:

- recommendations almost always `AVOID`
- risk categories almost always `MEDIUM_RISK`
- opportunity scores rarely exceed `70`
- individual signals are always `0`, `50`, or `100`

That usually means the model is not seeing enough variation, or the signal formulas need better normalization.

## What good variation looks like

Healthy distributions usually show:

- a spread of recommendation labels
- more than one risk category
- opportunity scores that span a meaningful range
- signal scores that vary across companies and over time

## Diagnosis before tuning

We diagnose first so we do not tune blindly.

If the distribution is flat, changing weights will not fix the root problem.
If the distribution is noisy, tuning may just overfit the noise.

The correct order is:

1. measure distributions
2. identify compression or missing variation
3. fix data or signal issues
4. then tune strategy weights
5. only later consider ML
