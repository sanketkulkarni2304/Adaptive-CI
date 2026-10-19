from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TestSpec:
    id: str
    command: list[str]
    duration_seconds: float = 1.0
    covers: tuple[str, ...] = ()
    priority: float = 0.5
    always_run: bool = False

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> TestSpec:
        command = value.get("command")
        if not isinstance(command, list) or not command:
            raise ValueError(f"{value.get('id', '<unknown>')}: command must be a non-empty list")
        duration = float(value.get("duration_seconds", 1.0))
        priority = float(value.get("priority", 0.5))
        if duration <= 0 or not 0 <= priority <= 1:
            raise ValueError("duration_seconds must be positive and priority must be between 0 and 1")
        return cls(
            id=str(value["id"]),
            command=[str(part) for part in command],
            duration_seconds=duration,
            covers=tuple(str(path) for path in value.get("covers", [])),
            priority=priority,
            always_run=bool(value.get("always_run", False)),
        )


@dataclass(frozen=True)
class TestStats:
    runs: int = 0
    failures: int = 0
    failure_ema: float = 0.0
    duration_ema: float | None = None
    last_run: str | None = None
    last_failed: bool = False


@dataclass(frozen=True)
class ScoredTest:
    test: TestSpec
    probability: float
    relevance: float
    base_value: float
    effective_duration: float
    history_staleness: float = 0.0
    failure_ema: float = 0.0


@dataclass
class Plan:
    budget_seconds: float
    changed_paths: list[str]
    selected: list[dict[str, Any]]
    estimated_duration_seconds: float
    generated_at: str
    selector: str = "marginal-greedy-v1"
    search: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TestOutcome:
    test_id: str
    status: str
    duration_seconds: float
    return_code: int | None = None
    output: str = ""


@dataclass
class RunResults:
    outcomes: list[TestOutcome] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "outcomes": [asdict(outcome) for outcome in self.outcomes],
        }


def load_manifest(path: str | Path) -> list[TestSpec]:
    raw = json.loads(Path(path).read_text())
    values = raw["tests"] if isinstance(raw, dict) else raw
    tests = [TestSpec.from_dict(value) for value in values]
    ids = [test.id for test in tests]
    if len(ids) != len(set(ids)):
        raise ValueError("test IDs must be unique")
    return tests


def write_json(path: str | Path, value: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(value, indent=2) + "\n")
