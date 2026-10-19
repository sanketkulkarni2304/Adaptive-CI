from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .models import TestOutcome, TestStats

SCHEMA = """
CREATE TABLE IF NOT EXISTS test_history (
    test_id TEXT PRIMARY KEY,
    runs INTEGER NOT NULL DEFAULT 0,
    failures INTEGER NOT NULL DEFAULT 0,
    failure_ema REAL NOT NULL DEFAULT 0,
    duration_ema REAL,
    last_run TEXT,
    last_failed INTEGER NOT NULL DEFAULT 0
)
"""


class HistoryStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.execute(SCHEMA)
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def get(self, test_id: str) -> TestStats:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """SELECT runs, failures, failure_ema, duration_ema, last_run, last_failed
                   FROM test_history WHERE test_id = ?""",
                (test_id,),
            ).fetchone()
        return TestStats(*row[:-1], last_failed=bool(row[-1])) if row else TestStats()

    def all(self) -> dict[str, TestStats]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT test_id, runs, failures, failure_ema, duration_ema,
                          last_run, last_failed FROM test_history"""
            ).fetchall()
        return {
            row[0]: TestStats(*row[1:-1], last_failed=bool(row[-1]))
            for row in rows
        }

    def record(self, outcome: TestOutcome, alpha: float = 0.25) -> None:
        failed = outcome.status in {"failed", "timeout"}
        old = self.get(outcome.test_id)
        failure_ema = alpha * float(failed) + (1 - alpha) * old.failure_ema
        duration_ema = (
            outcome.duration_seconds
            if old.duration_ema is None
            else alpha * outcome.duration_seconds + (1 - alpha) * old.duration_ema
        )
        with closing(self._connect()) as connection:
            connection.execute(
                """INSERT INTO test_history
                   (test_id, runs, failures, failure_ema, duration_ema, last_run, last_failed)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(test_id) DO UPDATE SET runs=excluded.runs,
                     failures=excluded.failures, failure_ema=excluded.failure_ema,
                     duration_ema=excluded.duration_ema, last_run=excluded.last_run,
                     last_failed=excluded.last_failed""",
                (
                    outcome.test_id,
                    old.runs + 1,
                    old.failures + int(failed),
                    failure_ema,
                    duration_ema,
                    datetime.now(timezone.utc).isoformat(),
                    int(failed),
                ),
            )
            connection.commit()

    def put(self, test_id: str, stats: TestStats) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """INSERT INTO test_history
                   (test_id, runs, failures, failure_ema, duration_ema, last_run, last_failed)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(test_id) DO UPDATE SET runs=excluded.runs,
                     failures=excluded.failures, failure_ema=excluded.failure_ema,
                     duration_ema=excluded.duration_ema, last_run=excluded.last_run,
                     last_failed=excluded.last_failed""",
                (
                    test_id,
                    stats.runs,
                    stats.failures,
                    stats.failure_ema,
                    stats.duration_ema,
                    stats.last_run,
                    int(stats.last_failed),
                ),
            )
            connection.commit()
