import json

from adaptive_ci.cli import main
from adaptive_ci.simulation import METHODS, run_simulation


def without_timing(report):
    copy = json.loads(json.dumps(report))
    for method in METHODS:
        copy["methods"][method].pop("selection_overhead_seconds")
    return copy


def test_simulation_is_seeded_and_reports_all_baselines():
    first = run_simulation(test_count=8, builds=6, budget=25, seed=9, iterations=8)
    second = run_simulation(test_count=8, builds=6, budget=25, seed=9, iterations=8)

    assert without_timing(first) == without_timing(second)
    assert set(first["methods"]) == set(METHODS)
    assert first["methods"]["alns-rl"]["q_updates"] == 48
    for metrics in first["methods"].values():
        assert 0 <= metrics["fault_detection_rate"] <= 1
        assert 0 <= metrics["mean_budget_utilization"] <= 1


def test_simulate_cli_writes_report(tmp_path, capsys):
    output = tmp_path / "simulation.json"

    status = main(
        [
            "simulate",
            "--tests",
            "6",
            "--builds",
            "4",
            "--budget",
            "20",
            "--seed",
            "5",
            "--iterations",
            "3",
            "--output",
            str(output),
        ]
    )

    report = json.loads(output.read_text())
    assert status == 0
    assert report["kind"] == "synthetic-mechanics-demo"
    assert report["config"]["tests"] == 6
    assert "ALNS-RL learning" in capsys.readouterr().out
