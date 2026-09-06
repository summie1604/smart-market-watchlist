"""The scalability report measures real domain work and labels its limits."""

from smart_watchlist.evaluation.load import run_load_validation


def test_load_validation_exercises_every_named_path() -> None:
    report = run_load_validation(iterations=5, workers=2)

    assert report.review_iterations == 5
    assert report.review_p95_ms > 0
    assert 0 < report.sqlite_review_p95_ms < 300
    assert report.concurrent_reviews_per_second > 0
    assert report.extraction_items == 500
    assert report.extractions_per_second > 0
    assert report.chart_sessions == 252
    assert report.peak_rss_mb > 0
    assert "does **not** prove" in report.markdown()
