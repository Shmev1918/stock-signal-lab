# Decisions

## Architectural Decision Log

### Decision: This is a personal local-first app, not SaaS.
Reason: Optimize for one user, not general commercial complexity.

### Decision: Use provider abstraction.
Reason: Market data providers can change without rewriting scoring.

### Decision: Store signals separately from scores.
Reason: Signals are evidence; scores are disposable.

### Decision: Use strategy profiles.
Reason: The same stock can be interpreted differently by different investing philosophies.

### Decision: Add decision journal.
Reason: Compare human decisions against engine recommendations over time.

### Decision: Alembic owns the Postgres schema.
Reason: create_all caused schema drift and migration inconsistency.

### Decision: ML should predict benchmark-relative outcomes, not exact prices.
Reason: Easier to evaluate honestly and less prone to false precision.
