from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from collections import defaultdict


@dataclass(frozen=True)
class SignalFeatureSpec:
    name: str
    category: str
    provider: str
    source_fields: tuple[str, ...]
    normalization_formula: str
    expected_range: str
    current_variation: str
    experiment_status: str
    predictive_status: str
    confidence: str
    known_limitations: str
    last_validated: str


LAST_VALIDATED = date.today().isoformat()

FEATURE_REGISTRY: tuple[SignalFeatureSpec, ...] = (
    SignalFeatureSpec(
        name="volatility",
        category="RISK",
        provider="internal",
        source_fields=("daily_prices.close", "daily_prices.price_date"),
        normalization_formula="normalized_score = clamp(100 - min(annualized_volatility * 250, 100))",
        expected_range="raw annualized volatility >= 0; normalized score 0-100",
        current_variation="Varies across real price histories; sensitive to price churn and series length.",
        experiment_status="baseline-tested",
        predictive_status="inconclusive",
        confidence="MEDIUM",
        known_limitations="Requires enough price rows to estimate stable annualized volatility.",
        last_validated=LAST_VALIDATED,
    ),
    SignalFeatureSpec(
        name="max_drawdown",
        category="RISK",
        provider="internal",
        source_fields=("daily_prices.close", "daily_prices.price_date"),
        normalization_formula="normalized_score = clamp(100 - min(abs(max_drawdown) * 100, 100))",
        expected_range="raw drawdown -100%..0%; normalized score 0-100",
        current_variation="Varies across live price histories and reflects the worst peak-to-trough decline.",
        experiment_status="baseline-tested",
        predictive_status="inconclusive",
        confidence="MEDIUM",
        known_limitations="Needs a meaningful history window; short histories can underestimate drawdown.",
        last_validated=LAST_VALIDATED,
    ),
    SignalFeatureSpec(
        name="revenue_growth_consistency",
        category="QUALITY",
        provider="internal",
        source_fields=("fundamentals.as_of_date", "fundamentals.revenue_growth"),
        normalization_formula="normalized_score = linear transform of revenue growth consistency over available fundamentals",
        expected_range="raw consistency roughly 0-1; normalized score 0-100",
        current_variation="Varies when multiple fundamental snapshots exist; can flatten when fundamentals are sparse.",
        experiment_status="baseline-tested",
        predictive_status="inconclusive",
        confidence="LOW",
        known_limitations="yfinance fundamentals are often partial, so historical consistency can be thin.",
        last_validated=LAST_VALIDATED,
    ),
    SignalFeatureSpec(
        name="roe",
        category="QUALITY",
        provider="internal",
        source_fields=("fundamentals.as_of_date", "fundamentals.return_on_equity"),
        normalization_formula="normalized_score = linear_score(return_on_equity, -0.10, 0.40, higher_is_better=True)",
        expected_range="raw ROE typically negative to strongly positive; normalized score 0-100",
        current_variation="Varies when return_on_equity is available; otherwise falls back toward neutral.",
        experiment_status="baseline-tested",
        predictive_status="inconclusive",
        confidence="LOW",
        known_limitations="Coverage is limited by provider fundamentals availability and stale snapshots.",
        last_validated=LAST_VALIDATED,
    ),
    SignalFeatureSpec(
        name="debt_to_equity",
        category="QUALITY",
        provider="internal",
        source_fields=("fundamentals.as_of_date", "fundamentals.debt_to_equity"),
        normalization_formula="normalized_score = linear_score(debt_to_equity, 0.0, 4.0, higher_is_better=False)",
        expected_range="raw debt/equity >= 0; normalized score 0-100",
        current_variation="Varies when debt_to_equity is reported; can be missing for some issuers.",
        experiment_status="baseline-tested",
        predictive_status="inconclusive",
        confidence="LOW",
        known_limitations="Fundamental debt ratios may be missing or inconsistent across providers.",
        last_validated=LAST_VALIDATED,
    ),
    SignalFeatureSpec(
        name="free_cash_flow_positive",
        category="QUALITY",
        provider="internal",
        source_fields=("fundamentals.as_of_date", "fundamentals.free_cash_flow"),
        normalization_formula="normalized_score = 100 if free_cash_flow > 0 else 0; missing data should be explicit",
        expected_range="raw free cash flow can be negative or positive; normalized score 0-100",
        current_variation="Varies only when free_cash_flow is populated; otherwise the signal can be missing-data limited.",
        experiment_status="baseline-tested",
        predictive_status="inconclusive",
        confidence="LOW",
        known_limitations="Positive/negative classification is only as good as the provider's free cash flow coverage.",
        last_validated=LAST_VALIDATED,
    ),
    SignalFeatureSpec(
        name="pe_ratio",
        category="VALUATION",
        provider="internal",
        source_fields=("fundamentals.as_of_date", "fundamentals.pe_ratio"),
        normalization_formula="normalized_score = linear_score(pe_ratio, 8.0, 45.0, higher_is_better=False)",
        expected_range="raw P/E usually positive and unbounded; normalized score 0-100",
        current_variation="Varies where trailing P/E is present; missing values are common for unprofitable names.",
        experiment_status="baseline-tested",
        predictive_status="inconclusive",
        confidence="MEDIUM",
        known_limitations="Unprofitable companies and partial fundamentals can flatten coverage.",
        last_validated=LAST_VALIDATED,
    ),
    SignalFeatureSpec(
        name="price_to_sales",
        category="VALUATION",
        provider="internal",
        source_fields=("fundamentals.as_of_date", "fundamentals.price_to_sales"),
        normalization_formula="normalized_score = linear_score(price_to_sales, 1.0, 15.0, higher_is_better=False)",
        expected_range="raw P/S usually positive and unbounded; normalized score 0-100",
        current_variation="Varies when sales-based valuation is available; typically broader than P/E coverage.",
        experiment_status="baseline-tested",
        predictive_status="inconclusive",
        confidence="MEDIUM",
        known_limitations="Comparability across sectors is limited and provider coverage can be partial.",
        last_validated=LAST_VALIDATED,
    ),
    SignalFeatureSpec(
        name="return_3m",
        category="MOMENTUM",
        provider="internal",
        source_fields=("daily_prices.close", "daily_prices.price_date"),
        normalization_formula="normalized_score = linear_score(3m return, -0.30, 0.30, higher_is_better=True)",
        expected_range="raw return roughly -100%..+100%; normalized score 0-100",
        current_variation="Varies on real price histories and is usually one of the most informative signals.",
        experiment_status="baseline-tested",
        predictive_status="inconclusive",
        confidence="MEDIUM",
        known_limitations="Requires enough lookback rows and can be noisy for thin histories.",
        last_validated=LAST_VALIDATED,
    ),
    SignalFeatureSpec(
        name="return_6m",
        category="MOMENTUM",
        provider="internal",
        source_fields=("daily_prices.close", "daily_prices.price_date"),
        normalization_formula="normalized_score = linear_score(6m return, -0.40, 0.40, higher_is_better=True)",
        expected_range="raw return roughly -100%..+100%; normalized score 0-100",
        current_variation="Varies across live data and tends to be smoother than 3m momentum.",
        experiment_status="baseline-tested",
        predictive_status="inconclusive",
        confidence="MEDIUM",
        known_limitations="Depends on having enough trading days before the as-of date.",
        last_validated=LAST_VALIDATED,
    ),
    SignalFeatureSpec(
        name="return_12m",
        category="MOMENTUM",
        provider="internal",
        source_fields=("daily_prices.close", "daily_prices.price_date"),
        normalization_formula="normalized_score = linear_score(12m return, -0.60, 0.80, higher_is_better=True)",
        expected_range="raw return roughly -100%..+100%; normalized score 0-100",
        current_variation="Varies on longer histories and captures broader trend persistence.",
        experiment_status="baseline-tested",
        predictive_status="inconclusive",
        confidence="MEDIUM",
        known_limitations="Long lookback windows can exclude newer listings or sparse histories.",
        last_validated=LAST_VALIDATED,
    ),
    SignalFeatureSpec(
        name="ma_50_vs_200",
        category="MOMENTUM",
        provider="internal",
        source_fields=("daily_prices.close", "daily_prices.price_date"),
        normalization_formula="normalized_score = linear_score((ma50 / ma200) - 1, -0.25, 0.25, higher_is_better=True)",
        expected_range="raw relative spread roughly -25%..+25% in normal conditions; normalized score 0-100",
        current_variation="Varies when at least 200 price rows exist; otherwise it falls back or stays neutral.",
        experiment_status="baseline-tested",
        predictive_status="inconclusive",
        confidence="MEDIUM",
        known_limitations="Requires long enough price history to calculate both moving averages.",
        last_validated=LAST_VALIDATED,
    ),
)


def group_feature_registry() -> dict[str, list[SignalFeatureSpec]]:
    grouped: dict[str, list[SignalFeatureSpec]] = defaultdict(list)
    for spec in FEATURE_REGISTRY:
        grouped[spec.category.upper()].append(spec)
    return dict(sorted(grouped.items()))


def render_feature_registry_markdown() -> str:
    lines: list[str] = [
        "# Feature Registry",
        "",
        "This document is generated from `app/signals/registry.py`.",
        "Do not edit the table content by hand; regenerate it from metadata instead.",
        "",
        f"Last generated: {LAST_VALIDATED}",
        "",
        "The registry is the canonical reference for signal metadata in analytics work.",
        "",
    ]
    for category, specs in group_feature_registry().items():
        lines.extend(
            [
                f"## {category}",
                "",
                "| Name | Provider | Source Fields | Normalization Formula | Expected Range | Current Variation | Experiment Status | Predictive Status | Confidence | Known Limitations | Last Validated |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for spec in specs:
            lines.append(
                "| "
                + " | ".join(
                    [
                        spec.name,
                        spec.provider,
                        ", ".join(spec.source_fields),
                        spec.normalization_formula,
                        spec.expected_range,
                        spec.current_variation,
                        spec.experiment_status,
                        spec.predictive_status,
                        spec.confidence,
                        spec.known_limitations,
                        spec.last_validated,
                    ]
                )
                + " |"
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
