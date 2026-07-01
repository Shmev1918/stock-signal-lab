from app.scoring.risk import RiskInputs, score_risk


def test_risk_scoring_ranges() -> None:
    score, category, signals = score_risk(RiskInputs(volatility=0.2, beta=1.1, debt_to_equity=0.5))
    assert 0 <= score <= 100
    assert category in {"STABLE", "MEDIUM_RISK", "HIGH_RISK", "SPECULATIVE"}
    assert signals

