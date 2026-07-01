from app.scoring.quality import QualityInputs, score_quality


def test_quality_scoring_ranges() -> None:
    score, positives, negatives = score_quality(
        QualityInputs(revenue_growth_consistency=0.7, return_on_equity=0.2, debt_to_equity=1.5)
    )
    assert 0 <= score <= 100
    assert positives
    assert negatives

