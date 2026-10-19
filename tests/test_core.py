from datetime import datetime, timedelta, timezone

from adaptive_ci.history import HistoryStore
from adaptive_ci.impact import impacted_tests, relevance
from adaptive_ci.models import TestOutcome as Outcome
from adaptive_ci.models import TestSpec as Spec
from adaptive_ci.models import TestStats as Stats
from adaptive_ci.scoring import score_tests
from adaptive_ci.selector import select_tests


def spec(name, duration=1.0, covers=("src/app.py",), priority=0.5, always=False):
    return Spec(name, ["python", "-c", "pass"], duration, covers, priority, always)


def test_impact_selects_matching_failed_and_always_tests():
    matching = spec("matching")
    unrelated = spec("unrelated", covers=("src/other.py",))
    failed = spec("failed", covers=("docs",))
    always = spec("always", covers=(), always=True)
    history = {"failed": Stats(last_failed=True)}

    selected = impacted_tests(
        [matching, unrelated, failed, always], ["src/app.py"], history
    )

    assert {test.id for test in selected} == {"matching", "failed", "always"}
    assert relevance(matching, ["src/app.py"]) == 1.0


def test_impact_includes_stale_tests():
    stale = spec("stale", covers=("src/other.py",))
    fresh = spec("fresh", covers=("src/other.py",))
    old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    recent = datetime.now(timezone.utc).isoformat()
    history = {"stale": Stats(runs=3, last_run=old), "fresh": Stats(runs=3, last_run=recent)}

    selected = impacted_tests([stale, fresh, spec("match")], ["src/app.py"], history)

    assert {test.id for test in selected} == {"stale", "match"}


def test_impact_falls_back_to_all_tests_when_mapping_is_empty():
    tests = [spec("one", covers=()), spec("two", covers=())]
    assert impacted_tests(tests, ["unknown.py"], {}) == tests


def test_selector_respects_budget_and_prefers_unique_coverage():
    tests = [
        spec("high", 4, ("src/a.py",), 1.0),
        spec("overlap", 4, ("src/a.py",), 0.8),
        spec("unique", 4, ("src/b.py",), 0.7),
    ]
    scored = score_tests(tests, ["src/a.py", "src/b.py"], {})

    plan = select_tests(scored, ["src/a.py", "src/b.py"], budget_seconds=8)

    assert plan.estimated_duration_seconds <= 8
    assert len(plan.selected) == 2
    assert "unique" in {entry["id"] for entry in plan.selected}


def test_always_run_tests_must_fit_budget():
    scored = score_tests([spec("mandatory", duration=5, always=True)], [], {})
    try:
        select_tests(scored, [], budget_seconds=4)
    except ValueError as error:
        assert "always-run" in str(error)
    else:
        raise AssertionError("expected an over-budget error")


def test_history_updates_failure_and_duration_ema(tmp_path):
    store = HistoryStore(tmp_path / "history.db")
    store.record(Outcome("test-a", "failed", 4.0, 1))
    store.record(Outcome("test-a", "passed", 2.0, 0))

    stats = store.get("test-a")
    assert stats.runs == 2
    assert stats.failures == 1
    assert stats.last_failed is False
    assert stats.failure_ema == 0.1875
    assert stats.duration_ema == 3.5
