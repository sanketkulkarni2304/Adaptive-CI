from __future__ import annotations

import random
import time
from datetime import datetime, timezone
from typing import Any

from .alns import ACTIONS, solution_objective
from .impact import relevance
from .models import ScoredTest, TestSpec, TestStats, write_json
from .scoring import score_tests
from .selector import select_tests

METHODS = ("random", "greedy", "alns", "alns-rl")


def _generate_tests(count: int, rng: random.Random) -> tuple[list[TestSpec], dict[str, float]]:
    unit_count = max(8, count // 2)
    units = [f"src/module_{index}.py" for index in range(unit_count)]
    tests = []
    failure_rates = {}
    for index in range(count):
        covers = tuple(rng.sample(units, rng.randint(2, min(4, unit_count))))
        test_id = f"synthetic-test-{index:03d}"
        tests.append(
            TestSpec(
                id=test_id,
                command=["synthetic"],
                duration_seconds=round(rng.uniform(3.0, 18.0), 3),
                covers=covers,
                priority=round(rng.uniform(0.2, 1.0), 3),
            )
        )
        failure_rates[test_id] = (
            rng.uniform(0.18, 0.42) if rng.random() < 0.25 else rng.uniform(0.01, 0.09)
        )
    return tests, failure_rates


def _random_selection(
    scored: list[ScoredTest], budget: float, rng: random.Random
) -> tuple[list[ScoredTest], float]:
    order = list(range(len(scored)))
    rng.shuffle(order)
    selected: set[int] = set()
    used = 0.0
    for index in order:
        if used + scored[index].effective_duration <= budget:
            selected.add(index)
            used += scored[index].effective_duration
    return [scored[index] for index in selected], solution_objective(selected, scored)


def _empty_metrics() -> dict[str, Any]:
    return {
        "selected_failures": 0,
        "available_failures": 0,
        "faulty_builds": 0,
        "detected_builds": 0,
        "budget_utilization_sum": 0.0,
        "objective_sum": 0.0,
        "selection_overhead_seconds": 0.0,
        "q_updates": 0,
        "per_build_detection": [],
    }


def _finalize(metrics: dict[str, Any], builds: int) -> dict[str, Any]:
    first = metrics.pop("per_build_detection")
    midpoint = max(1, len(first) // 2)

    def rate(values: list[tuple[int, int]]) -> float:
        detected = sum(item[0] for item in values)
        available = sum(item[1] for item in values)
        return detected / available if available else 1.0

    return {
        "fault_detection_rate": (
            metrics["selected_failures"] / metrics["available_failures"]
            if metrics["available_failures"]
            else 1.0
        ),
        "faulty_build_detection_rate": (
            metrics["detected_builds"] / metrics["faulty_builds"]
            if metrics["faulty_builds"]
            else 1.0
        ),
        "mean_budget_utilization": metrics["budget_utilization_sum"] / builds,
        "mean_objective": metrics["objective_sum"] / builds,
        "selection_overhead_seconds": metrics["selection_overhead_seconds"],
        "q_updates": metrics["q_updates"],
        "first_half_fault_detection_rate": rate(first[:midpoint]),
        "second_half_fault_detection_rate": rate(first[midpoint:]),
    }


def run_simulation(
    test_count: int = 25,
    builds: int = 100,
    budget: float = 60.0,
    seed: int = 42,
    iterations: int = 100,
) -> dict[str, Any]:
    if test_count < 4 or builds < 2 or budget <= 0 or iterations < 1:
        raise ValueError("simulation needs at least 4 tests, 2 builds, and positive limits")
    rng = random.Random(seed)
    tests, failure_rates = _generate_tests(test_count, rng)
    units = sorted({unit for test in tests for unit in test.covers})
    scenarios = []
    for _ in range(builds):
        changed = rng.sample(units, rng.randint(3, min(5, len(units))))
        failed = {
            test.id
            for test in tests
            if relevance(test, changed) > 0
            and rng.random() < min(0.8, failure_rates[test.id] * 1.5)
        }
        scenarios.append((changed, failed))

    history: dict[str, TestStats] = {}
    q_table: dict[str, list[float]] = {}
    metrics = {method: _empty_metrics() for method in METHODS}
    operator_counts: dict[str, int] = {}

    for build_index, (changed, failures) in enumerate(scenarios):
        candidates = [test for test in tests if relevance(test, changed) > 0]
        scored = score_tests(candidates, changed, history)
        available_failures = len(failures)
        for method in METHODS:
            began = time.perf_counter()
            if method == "random":
                selected, objective = _random_selection(
                    scored, budget, random.Random(seed + build_index * 101)
                )
                q_updates = 0
            else:
                plan = select_tests(
                    scored,
                    changed,
                    budget,
                    algorithm=method,
                    iterations=iterations,
                    seed=seed + build_index,
                    q_table=q_table if method == "alns-rl" else None,
                )
                selected_ids = {entry["id"] for entry in plan.selected}
                selected = [item for item in scored if item.test.id in selected_ids]
                objective = float(plan.search["objective"])
                q_updates = int(plan.search.get("q_updates", 0))
                if method == "alns-rl":
                    for key, count in plan.search.get("operator_counts", {}).items():
                        operator_counts[key] = operator_counts.get(key, 0) + count
            elapsed = time.perf_counter() - began
            selected_ids = {item.test.id for item in selected}
            detected = len(selected_ids & failures)
            used = sum(item.effective_duration for item in selected)
            data = metrics[method]
            data["selected_failures"] += detected
            data["available_failures"] += available_failures
            data["faulty_builds"] += int(available_failures > 0)
            data["detected_builds"] += int(available_failures > 0 and detected > 0)
            data["budget_utilization_sum"] += used / budget
            data["objective_sum"] += objective
            data["selection_overhead_seconds"] += elapsed
            data["q_updates"] += q_updates
            data["per_build_detection"].append((detected, available_failures))

        timestamp = datetime.now(timezone.utc).isoformat()
        for test in candidates:
            old = history.get(test.id, TestStats())
            failed = test.id in failures
            history[test.id] = TestStats(
                runs=old.runs + 1,
                failures=old.failures + int(failed),
                failure_ema=0.25 * int(failed) + 0.75 * old.failure_ema,
                duration_ema=test.duration_seconds,
                last_run=timestamp,
                last_failed=failed,
            )

    timeline = {}
    for method in METHODS:
        detected = available = 0
        points = []
        for found, total in metrics[method]["per_build_detection"]:
            detected, available = detected + found, available + total
            points.append(round(detected / available, 4) if available else 1.0)
        timeline[method] = points
    top_actions = {
        state: ACTIONS[max(range(len(values)), key=values.__getitem__)]
        for state, values in sorted(q_table.items())
    }
    catalog = [
        {
            "id": test.id,
            "duration_seconds": test.duration_seconds,
            "covers": list(test.covers),
            "priority": test.priority,
            "true_failure_rate": round(failure_rates[test.id], 4),
            "runs": history.get(test.id, TestStats()).runs,
            "observed_failure_rate": round(
                history[test.id].failures / history[test.id].runs, 4
            )
            if test.id in history and history[test.id].runs
            else 0.0,
            "last_failed": history.get(test.id, TestStats()).last_failed,
        }
        for test in tests
    ]

    return {
        "kind": "synthetic-mechanics-demo",
        "timeline": timeline,
        "operator_counts": dict(sorted(operator_counts.items(), key=lambda kv: -kv[1])[:15]),
        "q_policy": {
            state: {"destroy": a[0], "repair": a[1], "level": a[2], "q": round(max(q_table[state]), 3)}
            for state, a in top_actions.items()
        },
        "catalog": catalog,
        "disclaimer": (
            "Synthetic replay demonstrates algorithm mechanics; it is not evidence of "
            "production effectiveness."
        ),
        "config": {
            "tests": test_count,
            "builds": builds,
            "budget_seconds": budget,
            "seed": seed,
            "iterations_per_search": iterations,
        },
        "policy": {
            "states_visited": len(q_table),
            "learned_values": sum(
                value != 0.0 for values in q_table.values() for value in values
            ),
        },
        "methods": {method: _finalize(metrics[method], builds) for method in METHODS},
    }


def write_simulation_report(path: str, report: dict[str, Any]) -> None:
    write_json(path, report)


def format_simulation_summary(report: dict[str, Any]) -> str:
    lines = [
        "Synthetic mechanics demo (not production evidence)",
        "method    fault-detect  faulty-builds  budget-use  objective  overhead",
    ]
    for method in METHODS:
        result = report["methods"][method]
        lines.append(
            f"{method:<10}{result['fault_detection_rate']:>10.1%}"
            f"{result['faulty_build_detection_rate']:>15.1%}"
            f"{result['mean_budget_utilization']:>12.1%}"
            f"{result['mean_objective']:>11.3f}"
            f"{result['selection_overhead_seconds']:>10.3f}s"
        )
    rl = report["methods"]["alns-rl"]
    lines.append(
        "ALNS-RL learning: "
        f"{rl['q_updates']} Q-updates, {report['policy']['states_visited']} states, "
        f"fault detection {rl['first_half_fault_detection_rate']:.1%} -> "
        f"{rl['second_half_fault_detection_rate']:.1%}"
    )
    return "\n".join(lines)
