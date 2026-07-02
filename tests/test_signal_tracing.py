from __future__ import annotations

from datetime import date, timedelta

from sqlmodel import Session

from app.db.models import DailyPrice, Fundamental, Stock
from app.db.session import engine
from app.signals.momentum_signals import build_momentum_signals
from app.signals.quality_signals import build_quality_signals
from app.signals.risk_signals import build_risk_signals
from app.signals.valuation_signals import build_valuation_signals


def _price_rows(closes: list[float]) -> list[DailyPrice]:
    start = date.today() - timedelta(days=len(closes))
    rows: list[DailyPrice] = []
    for offset, close in enumerate(closes):
        rows.append(
            DailyPrice(
                ticker="AAA",
                price_date=start + timedelta(days=offset),
                open=close * 0.99,
                high=close * 1.01,
                low=close * 0.98,
                close=close,
                adj_close=close,
                volume=1_000_000 + offset,
                source="mock",
            )
        )
    return rows


def _fundamentals(
    *,
    revenue_growth: float | None = 0.1,
    return_on_equity: float | None = 0.15,
    debt_to_equity: float | None = 1.2,
    free_cash_flow: float | None = 1234.0,
    pe_ratio: float | None = 20.0,
    price_to_sales: float | None = 4.0,
) -> list[Fundamental]:
    return [
        Fundamental(
            ticker="AAA",
            as_of_date=date.today(),
            revenue_growth=revenue_growth,
            gross_margin=0.5,
            operating_margin=0.2,
            free_cash_flow=free_cash_flow,
            return_on_equity=return_on_equity,
            debt_to_equity=debt_to_equity,
            interest_coverage=4.0,
            pe_ratio=pe_ratio,
            forward_pe=pe_ratio,
            price_to_sales=price_to_sales,
            price_to_fcf=15.0,
            raw={},
            source="mock",
        )
    ]


def test_momentum_signals_vary_with_price_history() -> None:
    smooth = _price_rows([100 + i * 0.4 for i in range(260)])
    choppy = _price_rows([100 + ((-1) ** i) * (i * 0.8) for i in range(260)])

    signals_smooth = build_momentum_signals(smooth)
    signals_choppy = build_momentum_signals(choppy)

    assert signals_smooth[0].normalized_score != signals_choppy[0].normalized_score
    assert signals_smooth[1].normalized_score != signals_choppy[1].normalized_score
    assert signals_smooth[2].normalized_score != signals_choppy[2].normalized_score
    assert signals_smooth[3].normalized_score != signals_choppy[3].normalized_score


def test_risk_signals_vary_with_price_history() -> None:
    calm = _price_rows([100 + i * 0.1 for i in range(260)])
    volatile = _price_rows([100 + ((-1) ** i) * (i * 1.5) for i in range(260)])

    signals_calm = build_risk_signals(calm, [])
    signals_volatile = build_risk_signals(volatile, [])

    assert signals_calm[0].normalized_score != signals_volatile[0].normalized_score
    assert signals_calm[1].normalized_score != signals_volatile[1].normalized_score


def test_valuation_signals_vary_with_fundamentals() -> None:
    low_valuation = [Fundamental(ticker="AAA", as_of_date=date.today(), pe_ratio=10.0, price_to_sales=2.0)]
    high_valuation = [Fundamental(ticker="AAA", as_of_date=date.today(), pe_ratio=40.0, price_to_sales=12.0)]

    signals_low = build_valuation_signals(low_valuation)
    signals_high = build_valuation_signals(high_valuation)

    assert signals_low[0].normalized_score != signals_high[0].normalized_score
    assert signals_low[1].normalized_score != signals_high[1].normalized_score


def test_quality_signals_vary_with_fundamentals() -> None:
    good = _fundamentals()
    weak = _fundamentals(
        revenue_growth=-0.1,
        return_on_equity=0.05,
        debt_to_equity=3.5,
        free_cash_flow=-1_000.0,
        pe_ratio=40.0,
        price_to_sales=12.0,
    )

    signals_good = build_quality_signals(good)
    signals_weak = build_quality_signals(weak)

    assert signals_good[0].normalized_score != signals_weak[0].normalized_score
    assert signals_good[1].normalized_score != signals_weak[1].normalized_score
    assert signals_good[2].normalized_score != signals_weak[2].normalized_score
    assert signals_good[3].normalized_score != signals_weak[3].normalized_score


def test_free_cash_flow_positive_handles_positive_negative_and_missing() -> None:
    positive = next(row for row in build_quality_signals(_fundamentals(free_cash_flow=1234.0)) if row.name == "free_cash_flow_positive")
    negative = next(row for row in build_quality_signals(_fundamentals(free_cash_flow=-1234.0)) if row.name == "free_cash_flow_positive")
    missing = next(row for row in build_quality_signals(_fundamentals(free_cash_flow=None)) if row.name == "free_cash_flow_positive")

    assert positive.raw_value == 1.0
    assert positive.normalized_score == 100.0
    assert negative.raw_value == 0.0
    assert negative.normalized_score == 0.0
    assert missing.raw_value is None
    assert missing.normalized_score == 50.0


def test_signal_diagnostics_endpoint_reports_fallback_reasons(client) -> None:
    with Session(engine) as session:
        session.add(Stock(ticker="AAPL"))
        session.commit()

    response = client.get("/diagnostics/signals/AAPL")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "AAPL"
    assert payload["signals"]
    assert any(signal["fallback_used"] for signal in payload["signals"])
    assert any(signal["fallback_reason"] for signal in payload["signals"])
    assert any(signal["signal_name"] == "volatility" for signal in payload["signals"])


def test_signal_diagnostics_endpoint_includes_input_values(client) -> None:
    with Session(engine) as session:
        stock = Stock(ticker="MSFT")
        session.add(stock)
        session.commit()
        session.refresh(stock)
        for idx, close in enumerate([100.0, 101.0, 102.5, 103.0, 104.0, 105.5, 106.0, 107.0, 108.0, 109.0] * 30):
            session.add(
                DailyPrice(
                    ticker="MSFT",
                    price_date=date.today() - timedelta(days=300 - idx),
                    open=close * 0.99,
                    high=close * 1.01,
                    low=close * 0.98,
                    close=close,
                    adj_close=close,
                    volume=1_000_000 + idx,
                    source="mock",
                )
            )
        session.add(
            Fundamental(
                ticker="MSFT",
                as_of_date=date.today(),
                revenue_growth=0.12,
                gross_margin=0.61,
                operating_margin=0.35,
                free_cash_flow=10_000.0,
                return_on_equity=0.28,
                debt_to_equity=0.35,
                interest_coverage=18.0,
                pe_ratio=35.0,
                forward_pe=32.0,
                price_to_sales=12.0,
                price_to_fcf=28.0,
                raw={},
                source="mock",
            )
        )
        session.commit()

    response = client.get("/diagnostics/signals/MSFT")
    assert response.status_code == 200
    payload = response.json()
    volatility = next(signal for signal in payload["signals"] if signal["signal_name"] == "volatility")
    assert volatility["input_values"]["price_inputs"]["price_count"] > 0
    assert volatility["input_values"]["signal_type"] == "price"
    roe = next(signal for signal in payload["signals"] if signal["signal_name"] == "roe")
    assert roe["input_values"]["fundamental_inputs"]["return_on_equity"] == 0.28
    assert roe["input_values"]["signal_type"] == "fundamental"
