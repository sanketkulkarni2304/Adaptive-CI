import json
import sys

from adaptive_ci.runner import run_plan


def test_runner_records_pass_and_failure_and_writes_junit(tmp_path):
    plan = {
        "budget_seconds": 10,
        "selected": [
            {"id": "pass", "command": [sys.executable, "-c", "print('ok')"]},
            {"id": "fail", "command": [sys.executable, "-c", "raise SystemExit(3)"]},
        ],
    }
    output = tmp_path / "results.json"
    junit = tmp_path / "junit.xml"

    results = run_plan(plan, output, junit)

    assert [outcome.status for outcome in results.outcomes] == ["passed", "failed"]
    assert json.loads(output.read_text())["outcomes"][1]["return_code"] == 3
    assert 'failures="1"' in junit.read_text()


def test_runner_enforces_per_test_timeout(tmp_path):
    plan = {
        "budget_seconds": 5,
        "selected": [
            {
                "id": "slow",
                "command": [sys.executable, "-c", "import time; time.sleep(1)"],
            }
        ],
    }

    results = run_plan(plan, tmp_path / "results.json", per_test_timeout=0.05)

    assert results.outcomes[0].status == "timeout"
