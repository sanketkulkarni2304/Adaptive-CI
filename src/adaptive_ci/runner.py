from __future__ import annotations

import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from .models import RunResults, TestOutcome, write_json


def run_plan(
    plan: dict,
    output_path: str | Path,
    junit_path: str | Path | None = None,
    fail_fast: bool = False,
    per_test_timeout: float | None = None,
) -> RunResults:
    started = datetime.now(timezone.utc).isoformat()
    deadline = time.monotonic() + float(plan["budget_seconds"])
    outcomes: list[TestOutcome] = []
    for test in plan["selected"]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            outcomes.append(TestOutcome(test["id"], "skipped_budget", 0.0))
            continue
        timeout = min(remaining, per_test_timeout) if per_test_timeout else remaining
        began = time.monotonic()
        command = [
            sys.executable if argument == "{python}" else argument
            for argument in test["command"]
        ]
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            duration = time.monotonic() - began
            status = "passed" if result.returncode == 0 else "failed"
            output = (result.stdout + result.stderr)[-20_000:]
            outcome = TestOutcome(test["id"], status, duration, result.returncode, output)
        except subprocess.TimeoutExpired as exc:
            duration = time.monotonic() - began
            output = f"{exc.stdout or ''}{exc.stderr or ''}"[-20_000:]
            outcome = TestOutcome(test["id"], "timeout", duration, None, output)
        outcomes.append(outcome)
        if fail_fast and outcome.status != "passed":
            break

    results = RunResults(
        outcomes=outcomes,
        started_at=started,
        finished_at=datetime.now(timezone.utc).isoformat(),
    )
    write_json(output_path, results.to_dict())
    if junit_path:
        write_junit(junit_path, results)
    return results


def write_junit(path: str | Path, results: RunResults) -> None:
    failures = sum(outcome.status in {"failed", "timeout"} for outcome in results.outcomes)
    suite = ET.Element(
        "testsuite",
        name="adaptive-ci",
        tests=str(len(results.outcomes)),
        failures=str(failures),
    )
    for outcome in results.outcomes:
        case = ET.SubElement(
            suite, "testcase", name=outcome.test_id, time=f"{outcome.duration_seconds:.3f}"
        )
        if outcome.status in {"failed", "timeout"}:
            failure = ET.SubElement(case, "failure", message=outcome.status)
            failure.text = outcome.output
        elif outcome.status.startswith("skipped"):
            ET.SubElement(case, "skipped", message=outcome.status)
        if outcome.output:
            ET.SubElement(case, "system-out").text = outcome.output
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(suite).write(target, encoding="unicode", xml_declaration=True)
