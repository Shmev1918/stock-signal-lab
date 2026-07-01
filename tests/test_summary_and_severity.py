from __future__ import annotations

from app.scoring.summary import build_summary
from app.signals.base import signal_severity


def test_signal_severity_classification() -> None:
    assert signal_severity(92) == "STRONG_POSITIVE"
    assert signal_severity(68) == "POSITIVE"
    assert signal_severity(50) == "NEUTRAL"
    assert signal_severity(31) == "NEGATIVE"
    assert signal_severity(5) == "STRONG_NEGATIVE"


def test_summary_generation_is_deterministic() -> None:
    summary = build_summary(
        "MEDIUM_RISK",
        [
            {"signal_name": "volatility"},
            {"signal_name": "free_cash_flow_positive"},
        ],
        [
            {"signal_name": "debt_to_equity"},
            {"signal_name": "return_12m"},
        ],
        {"quality": 58.0, "valuation": 41.0},
    )

    assert summary == (
        "Moderate-risk stock with mixed fundamentals and elevated valuation."
        " Positive signals include low volatility and positive free cash flow."
        " Negative signals include elevated debt/equity and weak 12-month momentum."
    )
