# Analytics

## Intended Brain

Raw data

down arrow

normalized data

down arrow

feature snapshots

down arrow

signals

down arrow

strategies

down arrow

scores

down arrow

recommendations

down arrow

experiments

down arrow

ML

down arrow

evaluation

down arrow

continuous improvement

## Principles

- Machine learning does not replace the signal engine.
- ML observes historical outcomes and suggests improved weights or patterns.
- The system should begin with simple, explainable models.
- Do not start with neural networks.
- The first ML target should be benchmark-relative classification:
  - OUTPERFORM
  - NEUTRAL
  - UNDERPERFORM

## Walk-Forward Testing

Walk-forward testing means the system pretends it is at date T.

At that date:

1. Only use data available at date T.
2. Make a prediction or score.
3. Move forward 30, 90, 180, or 365 days.
4. Compare the prediction to the actual outcome.
5. Store the result.
6. Repeat.

This is the right way to evaluate an evolving investment model without cheating with future information.

## Major Risks

- lookahead bias
- survivorship bias
- overfitting
- missing data
- stale data
- revised fundamentals
- false precision
