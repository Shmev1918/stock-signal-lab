from __future__ import annotations

from collections.abc import Sequence


_SIGNAL_LABELS: dict[str, tuple[str, str]] = {
    "volatility": ("low volatility", "high volatility"),
    "max_drawdown": ("limited drawdown", "deep drawdown"),
    "revenue_growth_consistency": ("consistent revenue growth", "inconsistent revenue growth"),
    "roe": ("strong return on equity", "weak return on equity"),
    "debt_to_equity": ("manageable debt/equity", "elevated debt/equity"),
    "free_cash_flow_positive": ("positive free cash flow", "negative free cash flow"),
    "pe_ratio": ("reasonable P/E", "expensive P/E"),
    "price_to_sales": ("reasonable price-to-sales", "expensive price-to-sales"),
    "return_3m": ("strong 3-month momentum", "weak 3-month momentum"),
    "return_6m": ("strong 6-month momentum", "weak 6-month momentum"),
    "return_12m": ("strong 12-month momentum", "weak 12-month momentum"),
    "ma_50_vs_200": ("bullish moving-average trend", "bearish moving-average trend"),
}


def _phrase(signals: Sequence[dict[str, object]], positive: bool) -> str:
    names = []
    for signal in signals:
        name = str(signal.get("signal_name", ""))
        positive_label, negative_label = _SIGNAL_LABELS.get(name, (name.replace("_", " "), name.replace("_", " ")))
        label = positive_label if positive else negative_label
        if label and label not in names:
            names.append(label)
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return f"{', '.join(names[:-1])}, and {names[-1]}"


def build_summary(
    risk_category: str,
    positive_signals: Sequence[dict[str, object]],
    negative_signals: Sequence[dict[str, object]],
    scores: dict[str, float],
) -> str:
    risk_text = {
        "STABLE": "Stable-risk stock",
        "MEDIUM_RISK": "Moderate-risk stock",
        "HIGH_RISK": "High-risk stock",
        "SPECULATIVE": "Speculative stock",
    }.get(risk_category, "Mixed-risk stock")

    positives = _phrase(positive_signals[:3], positive=True)
    negatives = _phrase(negative_signals[:3], positive=False)

    quality = scores.get("quality", 50.0)
    valuation = scores.get("valuation", 50.0)
    if quality >= 60 and valuation >= 60:
        balance = "constructive fundamentals and supportive valuation"
    elif quality >= 60 and valuation <= 45:
        balance = "constructive fundamentals and elevated valuation"
    elif quality <= 40 and valuation >= 60:
        balance = "weak fundamentals and supportive valuation"
    elif quality <= 40 and valuation <= 45:
        balance = "weak fundamentals and elevated valuation"
    elif valuation <= 45:
        balance = "mixed fundamentals and elevated valuation"
    elif valuation >= 60:
        balance = "mixed fundamentals and supportive valuation"
    else:
        balance = "mixed fundamentals"

    summary = f"{risk_text} with {balance}."
    if positives:
        summary += f" Positive signals include {positives}."
    if negatives:
        summary += f" Negative signals include {negatives}."
    return summary
