import subprocess
from pathlib import Path

from adaptive_ci.shop_demo import (
    CHANGED_PATH,
    LONG_TEST,
    compare_shop,
    git_changed_files,
    load_shop_run,
)


def test_shop_selection_packs_bug_tests_and_skips_the_long_audit():
    report = compare_shop(Path(__file__).resolve().parents[1], budget=4.0, seed=1, iterations=200)

    assert report["model"] == "gaussian-naive-bayes"
    assert len(report["candidate_ids"]) == 14
    assert "test_catalog_lookup" not in report["candidate_ids"]
    assert report["methods"]["retest-all"]["fits_budget"] is False

    coverage = report["methods"]["coverage"]
    assert coverage["includes_long_test"] is True
    assert coverage["bug_tests"] == []

    random_selection = report["methods"]["random"]
    assert random_selection["ids"] == [LONG_TEST]
    assert random_selection["bug_tests"] == []

    selected = report["methods"]["alns-rl"]
    assert selected["fits_budget"] is True
    assert LONG_TEST not in selected["ids"]
    assert selected["bug_tests"] == [
        "test_percent_discount",
        "test_stack_discounts",
        "test_checkout_percent",
    ]


def test_dashboard_source_is_missing_until_a_demo_is_saved(tmp_path: Path):
    missing = load_shop_run(tmp_path)
    assert missing["available"] is False

    saved = tmp_path / ".adaptive-ci"
    saved.mkdir()
    (saved / "shop-demo.json").write_text(
        '{"suite_count": 24, "methods": {}, "search": {}}'
    )

    loaded = load_shop_run(tmp_path)
    assert loaded["available"] is True
    assert loaded["source"] == "Last adaptive-ci demo command"
    assert loaded["suite_count"] == 24


def test_git_diff_lists_a_changed_file(tmp_path: Path):
    target = tmp_path / "pricing.py"
    target.write_text("rate = 1\n")
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "add", "pricing.py"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=demo@example.com",
            "-c",
            "user.name=demo",
            "commit",
            "-m",
            "baseline",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    target.write_text("rate = 2\n")

    paths, command = git_changed_files(tmp_path)

    assert paths == ["pricing.py"]
    assert "git diff" in command
    assert CHANGED_PATH not in paths
