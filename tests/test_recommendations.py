from app.scoring.recommendation import recommend


def test_recommendation_labels() -> None:
    assert recommend(85, 60, 60, 75, 55) in {"ACCUMULATE", "STRONG_WATCH"}
    assert recommend(20, 20, 20, 20, 20) in {"AVOID", "SPECULATIVE"}

