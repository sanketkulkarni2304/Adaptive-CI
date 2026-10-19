from __future__ import annotations

from datetime import datetime, timezone

from .impact import relevance
from .models import ScoredTest, TestSpec, TestStats


def _heuristic_probability(stats: TestStats, relevance_score: float) -> float:
    if stats.runs == 0:
        return min(0.35, 0.08 + 0.22 * relevance_score)
    empirical = (stats.failures + 1) / (stats.runs + 5)
    return min(0.99, 0.55 * stats.failure_ema + 0.35 * empirical + 0.10 * relevance_score)


def _feature_row(test: TestSpec, changed_paths: list[str], stats: TestStats) -> list[float]:
    return [
        test.priority,
        relevance(test, changed_paths),
        stats.duration_ema or test.duration_seconds,
        stats.failure_ema,
    ]


def fit_failure_model(
    tests: list[TestSpec],
    changed_paths: list[str],
    history: dict[str, TestStats],
):
    """Return a fitted Gaussian Naive Bayes model, or None when it cannot be trained."""
    features: list[list[float]] = []
    labels: list[int] = []
    for test in tests:
        stats = history.get(test.id, TestStats())
        if stats.runs:
            features.append(_feature_row(test, changed_paths, stats))
            labels.append(int(stats.failures > 0))
    if len(features) < 10 or len(set(labels)) < 2:
        return None
    try:
        from sklearn.naive_bayes import GaussianNB
    except ImportError:
        return None
    return GaussianNB().fit(features, labels)


def score_tests(
    tests: list[TestSpec],
    changed_paths: list[str],
    history: dict[str, TestStats],
) -> list[ScoredTest]:
    model = fit_failure_model(tests, changed_paths, history)
    scored = []
    now = datetime.now(timezone.utc)
    for test in tests:
        stats = history.get(test.id, TestStats())
        rel = relevance(test, changed_paths)
        duration = stats.duration_ema or test.duration_seconds
        probability = _heuristic_probability(stats, rel)
        if model is not None:
            probability = float(model.predict_proba([_feature_row(test, changed_paths, stats)])[0][1])
        value = 0.55 * probability + 0.25 * rel + 0.15 * test.priority + 0.05 * stats.failure_ema
        age_days = (
            max(0.0, (now - datetime.fromisoformat(stats.last_run)).total_seconds() / 86400)
            if stats.last_run
            else 0.0
        )
        staleness = min(1.0, age_days / 30.0) if stats.runs and not stats.failures else 0.0
        scored.append(
            ScoredTest(
                test,
                probability,
                rel,
                value,
                max(0.01, duration),
                staleness,
                stats.failure_ema,
            )
        )
    return scored
