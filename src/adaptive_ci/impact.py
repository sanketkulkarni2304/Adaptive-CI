from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath

from .models import TestSpec, TestStats


def git_changed_paths(base: str = "HEAD~1", head: str = "HEAD") -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", base, head],
        check=True,
        capture_output=True,
        text=True,
    )
    return sorted({line.strip() for line in result.stdout.splitlines() if line.strip()})


def _matches(changed: str, covered: str) -> bool:
    changed_path = PurePosixPath(changed)
    covered_path = PurePosixPath(covered)
    return changed_path == covered_path or covered_path in changed_path.parents


def relevance(test: TestSpec, changed_paths: list[str]) -> float:
    if not changed_paths or not test.covers:
        return 0.0
    matched = sum(any(_matches(path, covered) for covered in test.covers) for path in changed_paths)
    return matched / len(changed_paths)


def is_stale(stats: TestStats, stale_days: float, now: datetime | None = None) -> bool:
    if not stats.last_run or stale_days <= 0:
        return False
    last_run = datetime.fromisoformat(stats.last_run)
    return (now or datetime.now(timezone.utc)) - last_run > timedelta(days=stale_days)


def impacted_tests(
    tests: list[TestSpec],
    changed_paths: list[str],
    history: dict[str, TestStats],
    stale_days: float = 7.0,
) -> list[TestSpec]:
    impacted = []
    for test in tests:
        stats = history.get(test.id, TestStats())
        if (
            test.always_run
            or stats.last_failed
            or is_stale(stats, stale_days)
            or relevance(test, changed_paths) > 0
        ):
            impacted.append(test)
    # Cold start and broad config changes should fail safe instead of selecting nothing.
    return impacted or tests
