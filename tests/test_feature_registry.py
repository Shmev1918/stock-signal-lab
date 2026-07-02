from __future__ import annotations

from app.signals.registry import FEATURE_REGISTRY, render_feature_registry_markdown


def test_feature_registry_covers_current_signals() -> None:
    names = {spec.name for spec in FEATURE_REGISTRY}
    assert names == {
        "volatility",
        "max_drawdown",
        "revenue_growth_consistency",
        "roe",
        "debt_to_equity",
        "free_cash_flow_positive",
        "pe_ratio",
        "price_to_sales",
        "return_3m",
        "return_6m",
        "return_12m",
        "ma_50_vs_200",
    }


def test_feature_registry_renders_markdown() -> None:
    markdown = render_feature_registry_markdown()
    assert "# Feature Registry" in markdown
    assert "## RISK" in markdown
    assert "## QUALITY" in markdown
    assert "## VALUATION" in markdown
    assert "## MOMENTUM" in markdown
    assert "free_cash_flow_positive" in markdown
    assert "ma_50_vs_200" in markdown
