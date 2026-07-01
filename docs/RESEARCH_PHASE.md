# Research Phase

The project is now entering the analytics and research phase.

Core question:

What actually predicts better investment outcomes?

## Priorities

- reliable data
- feature snapshots
- hypothesis testing
- benchmark-relative evaluation
- walk-forward experiments
- simple explainable ML only after experiments exist

## Experiment Harness

The first research tool is the experiment engine.

It should answer questions like:

- When the engine said opportunity_score >= 70, did it outperform SPY after 180 days?
- Did ACCUMULATE outperform WATCH and AVOID?
- Which strategy profile works best across different horizons?

Experiments must use stored historical data only.
They should never reach out to providers inside the evaluation loop.

Missing data should be recorded as skipped or unavailable, not hidden.

## Research Direction

The system should treat every analytical idea as a testable claim.

The priority order is:

1. collect reliable inputs
2. preserve historical snapshots
3. define hypotheses
4. evaluate against benchmarks
5. run walk-forward experiments
6. improve signal and strategy quality
7. add simple explainable ML only when the experiment process is stable

The research phase is about learning which signals, combinations, and strategy assumptions actually hold up in historical evaluation.
