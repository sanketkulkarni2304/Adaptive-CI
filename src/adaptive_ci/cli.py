from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from .history import HistoryStore
from .impact import git_changed_paths, impacted_tests
from .models import TestOutcome, load_manifest, write_json
from .policy import load_policy, save_policy
from .runner import run_plan
from .scoring import score_tests
from .selector import select_tests
from .shop_demo import run_shop_demo
from .simulation import (
    format_simulation_summary,
    run_simulation,
    write_simulation_report,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="adaptive-ci")
    parser.add_argument("--history", default=".adaptive-ci/history.db")
    commands = parser.add_subparsers(dest="action", required=True)

    init = commands.add_parser("init", help="create a starter manifest")
    init.add_argument("--manifest", default=".adaptive-ci/tests.json")

    discover = commands.add_parser("discover-pytest", help="create a manifest from pytest")
    discover.add_argument("--manifest", default=".adaptive-ci/tests.json")
    discover.add_argument("--duration", type=float, default=1.0)

    select = commands.add_parser("select", help="select impacted tests under a budget")
    select.add_argument("--manifest", default=".adaptive-ci/tests.json")
    select.add_argument("--base", default="HEAD~1")
    select.add_argument("--head", default="HEAD")
    select.add_argument("--changed", action="append", default=[])
    select.add_argument("--budget", type=float, required=True)
    select.add_argument("--overhead", type=float, default=0.0)
    select.add_argument("--stale-days", type=float, default=7.0)
    select.add_argument(
        "--algorithm", choices=("greedy", "alns", "alns-rl"), default="alns-rl"
    )
    select.add_argument("--iterations", type=int, default=500)
    select.add_argument("--seed", type=int, default=42)
    select.add_argument("--policy", default=".adaptive-ci/qtable.json")
    select.add_argument("--output", default=".adaptive-ci/plan.json")

    run = commands.add_parser("run", help="execute a generated plan")
    run.add_argument("--plan", default=".adaptive-ci/plan.json")
    run.add_argument("--output", default=".adaptive-ci/results.json")
    run.add_argument("--junit", default=".adaptive-ci/junit.xml")
    run.add_argument("--timeout", type=float)
    run.add_argument("--fail-fast", action="store_true")
    run.add_argument("--no-learn", action="store_true")

    learn = commands.add_parser("learn", help="import execution results")
    learn.add_argument("--results", default=".adaptive-ci/results.json")

    simulate = commands.add_parser("simulate", help="replay a synthetic CI workload")
    simulate.add_argument("--tests", type=int, default=25)
    simulate.add_argument("--builds", type=int, default=100)
    simulate.add_argument("--budget", type=float, default=60.0)
    simulate.add_argument("--seed", type=int, default=42)
    simulate.add_argument("--iterations", type=int, default=100)
    simulate.add_argument("--output", default=".adaptive-ci/simulation.json")

    dashboard = commands.add_parser("dashboard", help="serve the interactive showcase UI")
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", type=int, default=8000)

    demo = commands.add_parser("demo", help="demo Git-diff test selection on the shop example")
    demo.add_argument("--budget", type=float, default=4.0)
    demo.add_argument("--seed", type=int, default=1)
    demo.add_argument("--iterations", type=int, default=200)
    demo.add_argument("--no-execute", action="store_true")
    demo.add_argument("--keep-bug", action="store_true")
    return parser


def _init_manifest(path: str) -> None:
    if Path(path).exists():
        raise FileExistsError(f"{path} already exists")
    write_json(
        path,
        {
            "tests": [
                {
                    "id": "tests/test_example.py::test_example",
                    "command": [sys.executable, "-m", "pytest", "-q", "tests/test_example.py::test_example"],
                    "duration_seconds": 1.0,
                    "covers": ["src"],
                    "priority": 0.5,
                }
            ]
        },
    )


def _discover(path: str, duration: float) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        capture_output=True,
        text=True,
        check=True,
    )
    node_ids = [
        line.strip()
        for line in result.stdout.splitlines()
        if "::" in line and not line.startswith((" ", "="))
    ]
    tests = [
        {
            "id": node_id,
            "command": [sys.executable, "-m", "pytest", "-q", node_id],
            "duration_seconds": duration,
            "covers": [],
            "priority": 0.5,
        }
        for node_id in node_ids
    ]
    write_json(path, {"tests": tests})
    print(f"Discovered {len(tests)} tests in {path}; add covers paths for impact analysis.")


def _learn(store: HistoryStore, path: str) -> None:
    values = json.loads(Path(path).read_text())
    for value in values["outcomes"]:
        if value["status"] != "skipped_budget":
            store.record(TestOutcome(**value))


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.action == "init":
            _init_manifest(args.manifest)
            print(f"Created {args.manifest}")
            return 0
        if args.action == "discover-pytest":
            _discover(args.manifest, args.duration)
            return 0
        if args.action == "dashboard":
            from .dashboard import serve

            serve(args.host, args.port)
            return 0
        if args.action == "demo":
            return run_shop_demo(
                budget=args.budget,
                seed=args.seed,
                iterations=args.iterations,
                execute=not args.no_execute,
                keep_bug=args.keep_bug,
            )
        if args.action == "simulate":
            report = run_simulation(
                args.tests, args.builds, args.budget, args.seed, args.iterations
            )
            write_simulation_report(args.output, report)
            print(format_simulation_summary(report))
            print(f"Detailed report: {args.output}")
            return 0

        store = HistoryStore(args.history)
        if args.action == "select":
            tests = load_manifest(args.manifest)
            changed = sorted(set(args.changed or git_changed_paths(args.base, args.head)))
            history = store.all()
            candidates = impacted_tests(tests, changed, history, args.stale_days)
            q_table = load_policy(args.policy) if args.algorithm == "alns-rl" else None
            plan = select_tests(
                score_tests(candidates, changed, history),
                changed,
                args.budget,
                args.overhead,
                algorithm=args.algorithm,
                iterations=args.iterations,
                seed=args.seed,
                q_table=q_table,
            )
            if q_table is not None:
                save_policy(args.policy, q_table)
            write_json(args.output, plan.to_dict())
            print(
                f"Selected {len(plan.selected)}/{len(candidates)} tests; "
                f"estimated {plan.estimated_duration_seconds:.2f}s/{plan.budget_seconds:.2f}s."
            )
            return 0
        if args.action == "run":
            plan = json.loads(Path(args.plan).read_text())
            results = run_plan(plan, args.output, args.junit, args.fail_fast, args.timeout)
            if not args.no_learn:
                _learn(store, args.output)
            failed = sum(outcome.status in {"failed", "timeout"} for outcome in results.outcomes)
            print(f"Executed {len(results.outcomes)} tests; {failed} failed.")
            return int(failed > 0)
        if args.action == "learn":
            _learn(store, args.results)
            print(f"Imported results from {args.results}")
            return 0
    except (FileNotFoundError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"adaptive-ci: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
