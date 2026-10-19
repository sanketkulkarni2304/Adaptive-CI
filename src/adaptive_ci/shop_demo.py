from __future__ import annotations

import json
import os
import subprocess
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .alns import ACTIONS
from .baselines import select_coverage, select_history, select_ml_rank, select_random
from .history import HistoryStore
from .impact import impacted_tests
from .models import TestOutcome, TestSpec, TestStats, load_manifest, write_json
from .policy import save_policy
from .runner import run_plan
from .scoring import fit_failure_model, score_tests
from .selector import select_tests

CHANGED_PATH = "examples/shop-demo/shop/pricing.py"
MANIFEST_PATH = "examples/shop-demo/tests.json"
BUG_TESTS = ("test_percent_discount", "test_stack_discounts", "test_checkout_percent")
LONG_TEST = "test_pricing_audit"
CORRECT_RATE = "    rate = percent / 100\n"
BUGGY_RATE = "    rate = percent / 200\n"
SEEDED_FAILURES = {
    "test_percent_discount": (20, 11, 0.62),
    "test_stack_discounts": (18, 9, 0.58),
    "test_checkout_percent": (15, 8, 0.60),
    "test_coupon_discount": (16, 7, 0.40),
    "test_bulk_discount": (14, 6, 0.36),
    "test_zero_percent": (12, 4, 0.22),
    LONG_TEST: (20, 0, 0.0),
}


def project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "pyproject.toml").exists() and (candidate / MANIFEST_PATH).exists():
            return candidate
    raise FileNotFoundError("run this command from the Adaptive CI project")


def git_changed_files(root: Path) -> tuple[list[str], str]:
    probe = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode != 0 or probe.stdout.strip() != "true":
        return [], "not-a-git-repository"
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return [], "not-a-git-repository"
    paths = sorted({line.strip() for line in result.stdout.splitlines() if line.strip()})
    return paths, "git diff --name-only --diff-filter=ACMR HEAD"


def _plant(path: Path) -> str:
    original = path.read_text()
    if CORRECT_RATE not in original:
        raise RuntimeError(
            "pricing.py no longer has `rate = percent / 100`. Restore it before repeating the demo."
        )
    path.write_text(original.replace(CORRECT_RATE, BUGGY_RATE, 1))
    return original


def _diff_text(root: Path, original: str, pricing: Path, git_paths: list[str]) -> str:
    if CHANGED_PATH in git_paths:
        result = subprocess.run(
            ["git", "diff", "--no-color", "-U2", "HEAD", "--", CHANGED_PATH],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.stdout.strip():
            return result.stdout
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        before = base / "before" / CHANGED_PATH
        after = base / "after" / CHANGED_PATH
        before.parent.mkdir(parents=True)
        after.parent.mkdir(parents=True)
        before.write_text(original)
        after.write_text(pricing.read_text())
        result = subprocess.run(
            [
                "git",
                "diff",
                "--no-color",
                "--no-prefix",
                "--no-index",
                "--",
                str(before.relative_to(base)),
                str(after.relative_to(base)),
            ],
            cwd=base,
            capture_output=True,
            text=True,
            check=False,
        )
    return result.stdout.replace("before/", "a/").replace("after/", "b/")


def _seed(store: HistoryStore, tests: list[TestSpec]) -> None:
    seen_at = datetime.now(timezone.utc).isoformat()
    for test in tests:
        if CHANGED_PATH not in test.covers:
            continue
        runs, failures, ema = SEEDED_FAILURES.get(test.id, (10, 0, 0.0))
        store.put(
            test.id,
            TestStats(runs, failures, ema, test.duration_seconds, seen_at, False),
        )


def _ids(selected: list) -> list[str]:
    names = []
    for item in selected:
        names.append(item.test.id if hasattr(item, "test") else item["id"])
    return names


def _seconds(selected: list) -> float:
    total = 0.0
    for item in selected:
        total += item.effective_duration if hasattr(item, "effective_duration") else item["estimated_duration_seconds"]
    return total


def _method_row(name: str, selected: list, budget: float) -> dict:
    names = _ids(selected)
    seconds = _seconds(selected)
    return {
        "method": name,
        "ids": names,
        "count": len(names),
        "seconds": round(seconds, 3),
        "fits_budget": seconds <= budget + 1e-9,
        "bug_tests": [test_id for test_id in BUG_TESTS if test_id in names],
        "includes_long_test": LONG_TEST in names,
    }


def compare_shop(
    root: Path,
    budget: float = 4.0,
    seed: int = 1,
    iterations: int = 200,
) -> dict:
    tests = load_manifest(root / MANIFEST_PATH)
    history_path = root / ".adaptive-ci" / "shop-demo-history.db"
    if history_path.exists():
        history_path.unlink()
    store = HistoryStore(history_path)
    _seed(store, tests)
    history = store.all()
    changed = [CHANGED_PATH]
    candidates = impacted_tests(tests, changed, history)
    scored = score_tests(candidates, changed, history)
    model_name = (
        "gaussian-naive-bayes"
        if fit_failure_model(candidates, changed, history) is not None
        else "cold-start-heuristic"
    )
    q_table: dict[str, list[float]] = {}
    plans = {
        "greedy": select_tests(scored, changed, budget, algorithm="greedy", seed=seed),
        "alns": select_tests(
            scored, changed, budget, algorithm="alns", iterations=iterations, seed=seed
        ),
        "alns-rl": select_tests(
            scored,
            changed,
            budget,
            algorithm="alns-rl",
            iterations=iterations,
            seed=seed,
            q_table=q_table,
        ),
    }
    rows = [
        _method_row("retest-all", scored, budget),
        _method_row("random", select_random(scored, budget, seed), budget),
        _method_row("coverage", select_coverage(scored, budget), budget),
        _method_row("history", select_history(scored, budget), budget),
        _method_row("ml-rank", select_ml_rank(scored, budget), budget),
    ]
    rows.extend(_method_row(name, plan.selected, budget) for name, plan in plans.items())
    full_seconds = sum(test.duration_seconds for test in tests)
    return {
        "changed": changed,
        "budget_seconds": budget,
        "seed": seed,
        "model": model_name,
        "suite_count": len(tests),
        "suite_seconds": round(full_seconds, 3),
        "candidate_ids": [test.id for test in candidates],
        "scores": [
            {
                "id": item.test.id,
                "duration_seconds": round(item.effective_duration, 3),
                "relevance": round(item.relevance, 3),
                "priority": item.test.priority,
                "failure_ema": round(item.failure_ema, 3),
                "failure_probability": round(item.probability, 3),
                "value": round(item.base_value, 3),
                "covers": len(item.test.covers),
            }
            for item in sorted(scored, key=lambda item: item.base_value / item.effective_duration, reverse=True)
        ],
        "methods": {row["method"]: row for row in rows},
        "search": plans["alns-rl"].search,
        "plan": plans["alns-rl"].to_dict(),
        "q_table": q_table,
        "history_path": str(history_path),
    }


def format_shop_demo(report: dict, diff_text: str, git_label: str, git_paths: list[str]) -> str:
    budget = report["budget_seconds"]
    lines = [
        "Shop demo: choose tests for a Git change inside a fixed time budget",
        "",
        f"Full suite: {report['suite_count']} tests, about {report['suite_seconds']:.1f}s",
        f"CI budget: {budget:.1f}s",
        "",
        "Git change",
        git_label,
    ]
    if git_paths:
        lines.extend(git_paths)
    else:
        lines.append(CHANGED_PATH)
    if len(git_paths) > 1:
        lines.append("Other dirty files are listed above. This scenario selects tests for pricing.py only.")
    lines.extend(["", diff_text.rstrip(), "", "Impact"])
    skipped = report["suite_count"] - len(report["candidate_ids"])
    lines.append(
        f"{len(report['candidate_ids'])} tests touch {CHANGED_PATH}. "
        f"{skipped} tests do not, so they are not candidates."
    )
    lines.extend(["", f"Failure model: {report['model']}", ""])
    lines.append(
        "Naive Bayes is nearly certain here because the seeded history splits cleanly into past failures and past passes."
    )
    lines.append(f"{'test':<28}{'secs':>6}{'covers':>8}{'pri':>6}{'hist':>7}{'P(fail)':>8}{'value':>7}")
    for row in report["scores"]:
        lines.append(
            f"{row['id']:<28}{row['duration_seconds']:>6.2f}{row['covers']:>8}"
            f"{row['priority']:>6.2f}{row['failure_ema']:>7.2f}"
            f"{row['failure_probability']:>8.2f}{row['value']:>7.2f}"
        )
    lines.extend(
        [
            "",
            f"Same candidates, same {budget:.1f}s budget",
            f"{'method':<12}{'tests':>6}{'time':>8}{'fits':>6}{'bug tests':>11}{'long test':>11}",
        ]
    )
    for name in ("retest-all", "random", "coverage", "history", "ml-rank", "greedy", "alns", "alns-rl"):
        row = report["methods"][name]
        lines.append(
            f"{name:<12}{row['count']:>6}{row['seconds']:>8.2f}"
            f"{('yes' if row['fits_budget'] else 'no'):>6}"
            f"{len(row['bug_tests']):>8}/3"
            f"{('yes' if row['includes_long_test'] else 'no'):>11}"
        )
    chosen = report["methods"]["alns-rl"]
    lines.extend(["", "ALNS-RL selected:", "  " + ", ".join(chosen["ids"])])
    search = report["search"]
    lines.append(
        "Search: "
        f"{search['iterations']} iterations, {search['accepted_moves']} accepted moves, "
        f"{search['improvements']} improvements, {search['q_updates']} Q-table updates."
    )
    random_row = report["methods"]["random"]
    coverage_row = report["methods"]["coverage"]
    lines.append(
        f"Random kept {random_row['count']} test(s) and {len(random_row['bug_tests'])} of the 3 tests that catch this bug."
    )
    lines.append(
        "Coverage prefers the long audit because it lists the most files. "
        f"It kept {len(coverage_row['bug_tests'])} of those 3 tests."
    )
    lines.append(
        "History, ML ranking, greedy, ALNS, and ALNS-RL skip that long test and pack the shorter tests. "
        f"They kept {len(chosen['bug_tests'])} of the 3 tests that catch this bug."
    )
    lines.append(
        "On this small candidate list those five methods land on the same plan. "
        "ALNS-RL still records the moves it tried, and the saved Q-table is what a later build reuses."
    )
    return "\n".join(lines)


def format_execution(results) -> str:
    lines = ["", "Executed ALNS-RL plan"]
    for outcome in results.outcomes:
        lines.append(f"  {outcome.status:<16}{outcome.duration_seconds:5.2f}s  {outcome.test_id}")
    failed = [outcome for outcome in results.outcomes if outcome.status == "failed"]
    lines.append("")
    if failed:
        lines.append(
            f"The selected plan failed {len(failed)} test(s) inside the budget. "
            "That is the bug the Git change introduced."
        )
    else:
        lines.append("The selected plan did not fail a test. The demo did not catch the planted bug.")
    lines.append("Failure history was updated from this build. Test priority in the manifest was not changed.")
    return "\n".join(lines)


@contextmanager
def _working_directory(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _policy_summary(q_table: dict[str, list[float]]) -> dict[str, dict]:
    summary = {}
    for state, values in sorted(q_table.items()):
        if not values:
            continue
        index = max(range(len(values)), key=values.__getitem__)
        destroy, repair, level = ACTIONS[index]
        summary[state] = {
            "destroy": destroy,
            "repair": repair,
            "level": level,
            "q": round(max(values), 3),
        }
    return summary


def load_shop_run(root: Path | None = None) -> dict:
    """Return the report saved by the last `adaptive-ci demo` command."""
    root = root.resolve() if root is not None else project_root()
    report_path = root / ".adaptive-ci" / "shop-demo.json"
    if not report_path.exists():
        return {
            "available": False,
            "message": "No shop run saved yet. Run adaptive-ci demo, then press Refresh.",
        }
    report = json.loads(report_path.read_text())
    report.pop("history_path", None)
    report.pop("plan", None)
    report.pop("q_table", None)
    if "q_policy" not in report:
        policy_path = root / ".adaptive-ci" / "shop-demo-qtable.json"
        if policy_path.exists():
            from .policy import load_policy

            report["q_policy"] = _policy_summary(load_policy(policy_path))
    if "run" not in report:
        results_path = root / ".adaptive-ci" / "shop-demo-results.json"
        if results_path.exists():
            saved = json.loads(results_path.read_text())
            report["run"] = {
                "started_at": saved.get("started_at", ""),
                "finished_at": saved.get("finished_at", ""),
                "outcomes": [
                    {
                        "test_id": outcome["test_id"],
                        "status": outcome["status"],
                        "duration_seconds": round(float(outcome["duration_seconds"]), 3),
                    }
                    for outcome in saved.get("outcomes", [])
                ],
            }
    report["available"] = True
    report["source"] = "Last adaptive-ci demo command"
    return report


def run_shop_demo(
    root: Path | None = None,
    *,
    budget: float = 4.0,
    seed: int = 1,
    iterations: int = 200,
    execute: bool = True,
    keep_bug: bool = False,
) -> int:
    root = project_root(root)
    pricing = root / CHANGED_PATH
    original = _plant(pricing)
    try:
        git_paths, git_command = git_changed_files(root)
        if CHANGED_PATH in git_paths:
            label = f"$ {git_command}"
        else:
            label = (
                "This folder has no Git baseline for the shop file yet.\n"
                "$ git diff --no-color --no-index  (original pricing.py  ->  planted bug)"
            )
        report = compare_shop(root, budget, seed, iterations)
        q_table = report.pop("q_table")
        save_policy(root / ".adaptive-ci" / "shop-demo-qtable.json", q_table)
        diff_text = _diff_text(root, original, pricing, git_paths)
        print(format_shop_demo(report, diff_text, label, git_paths))
        report["git"] = {"label": label, "paths": git_paths, "diff": diff_text}
        report["q_policy"] = _policy_summary(q_table)
        report["run"] = None
        story_holds = (
            report["model"] == "gaussian-naive-bayes"
            and "test_percent_discount" in report["methods"]["alns-rl"]["ids"]
            and LONG_TEST not in report["methods"]["alns-rl"]["ids"]
            and report["methods"]["alns-rl"]["fits_budget"]
            and report["methods"]["coverage"]["includes_long_test"]
            and not report["methods"]["coverage"]["bug_tests"]
        )
        if execute:
            runnable = dict(report["plan"])
            # Selection already enforced the CI budget. Each selected test then starts
            # its own process, so the runner gets a little extra time for that startup.
            startup = 0.5 * len(runnable["selected"])
            runnable["budget_seconds"] = runnable["estimated_duration_seconds"] + startup
            print(
                f"\nRunning {len(runnable['selected'])} selected tests. "
                f"Their runtime is {report['plan']['estimated_duration_seconds']:.2f}s, "
                f"inside the {budget:.2f}s budget. "
                f"The runner allows {startup:.1f}s more so process startup does not drop a selected test."
            )
            with _working_directory(root):
                results = run_plan(
                    runnable,
                    root / ".adaptive-ci" / "shop-demo-results.json",
                    root / ".adaptive-ci" / "shop-demo-junit.xml",
                )
            store = HistoryStore(report["history_path"])
            for outcome in results.outcomes:
                if outcome.status != "skipped_budget":
                    store.record(TestOutcome(**outcome.__dict__))
            print(format_execution(results))
            report["run"] = {
                "started_at": results.started_at,
                "finished_at": results.finished_at,
                "outcomes": [
                    {
                        "test_id": outcome.test_id,
                        "status": outcome.status,
                        "duration_seconds": round(outcome.duration_seconds, 3),
                    }
                    for outcome in results.outcomes
                ],
            }
            updated = store.get("test_percent_discount")
            print(
                "test_percent_discount now has "
                f"{updated.failures} failures in {updated.runs} runs "
                f"(failure ema {updated.failure_ema:.2f})."
            )
            caught = any(
                outcome.status == "failed" and outcome.test_id in BUG_TESTS
                for outcome in results.outcomes
            )
            story_holds = story_holds and caught
        report.pop("plan", None)
        report.pop("history_path", None)
        write_json(root / ".adaptive-ci" / "shop-demo.json", report)
        print(f"\nSaved report: {root / '.adaptive-ci' / 'shop-demo.json'}")
        return 0 if story_holds else 1
    finally:
        if not keep_bug:
            pricing.write_text(original)
