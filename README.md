# Adaptive CI

Adaptive CI chooses which tests to run after a code change when there is not enough time to run the whole suite.

A full suite can take a long time. A pipeline often has only a short budget. This project looks at the changed file, keeps the tests that touch it, scores those tests, and packs the best ones into the budget.

## What is implemented

- **Change impact.** A test is a candidate when its `covers` paths match the changed file, it is marked always-run, it failed last time, or it has not run for 7 days. If nothing matches, every test is kept so the pipeline does not skip the suite by accident.
- **Scoring.** Each candidate gets a score from its duration, how much of the change it covers, its priority, and how often it has failed. After enough pass/fail history exists, Gaussian Naive Bayes estimates the chance of failure. Before that, a simple formula is used.
- **Budget packing.** The chosen tests must fit the time budget. A long test can crowd out several shorter ones, so the selector treats this as a packing problem.
- **Greedy.** Picks the best remaining test that still fits, and never removes a pick.
- **ALNS.** Starts from the greedy plan, then removes and reinserts groups of tests to look for a better combination.
- **ALNS-RL.** Uses the same search, with a small reinforcement-learning table that remembers which remove-and-insert moves worked. The table is saved and reused.
- **Other comparisons.** Random selection, coverage-first selection, history-first selection, and machine-learning ranking with a budget cutoff.
- **Run and learn.** The selected tests run one after another. Failures and durations are saved in a local database. The next selection can use that history.
- **Shop demo.** A 24-test shop with a one-line pricing bug, a 4-second budget, and a side-by-side comparison.
- **Web dashboard.** Two separate views. Shop run can replay the shop demo or show the last saved run. Simulation shows a made-up series of builds.

## What this demo is enough to show

It is enough to show the main project story:

1. The full suite does not fit the budget.
2. The Git change limits the candidates.
3. Tests are scored from cost, coverage, priority, history, and Naive Bayes.
4. Random selection and coverage-first selection can miss the bug.
5. The budget-aware methods keep the tests that catch the bug.
6. Those tests actually fail, and the failure history is updated.

It is not enough to claim that ALNS-RL is better than greedy. On the shop change, greedy, ALNS, and ALNS-RL choose the same seven tests. A larger replay is available in the dashboard, but that replay is synthetic and is not production evidence.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,ml]"
```

Install the `ml` extra. Without it, Naive Bayes stays off and the simple formula is used.

## Demo the shop change

From the project folder:

```bash
source .venv/bin/activate
adaptive-ci demo
```

This takes about 8 seconds. It prints the diff, the scores, the comparison, and then runs the selected tests. The pricing file is restored at the end.

Useful variants:

```bash
adaptive-ci demo --no-execute
adaptive-ci demo --keep-bug
```

`--no-execute` prints the comparison only. `--keep-bug` leaves the broken discount in `examples/shop-demo/shop/pricing.py`.

### Why this works without a Git commit

Git is installed on the computer, but this project folder is not a Git repository. There is no `.git` directory and no commit.

`adaptive-ci demo` still shows a diff. It writes the original `pricing.py` and the broken `pricing.py` into a temporary folder, then runs:

```bash
git diff --no-index
```

`--no-index` compares two files. It does not look at commits, branches, or `HEAD`. That is why the demo works before the first commit.

### Test it against a real Git diff

Do this once to create the baseline commit. The correct discount must be what gets committed. `.gitignore` already leaves out `.venv/` and `.adaptive-ci/`.

```bash
git init
git add .gitignore README.md pyproject.toml src tests examples .github
git commit -m "Baseline with the correct discount"
```

Run the demo again:

```bash
adaptive-ci demo --keep-bug
```

The Git section should now say:

```text
$ git diff --name-only --diff-filter=ACMR HEAD
examples/shop-demo/shop/pricing.py
```

That is a real repository diff: the uncommitted edit versus the baseline commit. `--keep-bug` leaves the broken line in place so you can inspect it yourself:

```bash
git diff --name-only HEAD
git diff -- examples/shop-demo/shop/pricing.py
```

Put the file back when you are finished:

```bash
git restore -- examples/shop-demo/shop/pricing.py
```

To test the committed range used by `adaptive-ci select`, keep the bug, commit it, and diff the last two commits:

```bash
git add examples/shop-demo/shop/pricing.py
git commit -m "Introduce the pricing bug"
git diff --name-only HEAD~1 HEAD
adaptive-ci select \
  --manifest examples/shop-demo/tests.json \
  --base HEAD~1 \
  --head HEAD \
  --budget 4
```

`select` reads only committed changes between `--base` and `--head`. It does not use the shop demo's seeded failure history, so its plan can differ from `adaptive-ci demo`. Use the demo for the full comparison. Use `select` to show a real `HEAD~1` to `HEAD` diff.

## Demo in the browser

The dashboard has two separate views. They do not share tabs or numbers.

```bash
source .venv/bin/activate
adaptive-ci demo
adaptive-ci dashboard
```

Open http://127.0.0.1:8000.

**Shop run** is the view that opens first. Opening the page does not run anything. It shows the last saved demo. If nothing has been saved yet, the page says so.

**Run shop demo** is the button to use during a presentation. It does the same work as typing `adaptive-ci demo`: it plants the pricing bug, selects tests, runs the selected tests, saves the result, and restores `pricing.py`. The page then shows that result. It takes about 8 seconds. The button does not create a second, different result.

**Refresh from last command** does not run the tests again. Use it when you already ran `adaptive-ci demo` in the terminal and want the page to load those saved files.

After a run, Shop run has five tabs:

1. **Change** shows the Git diff from that command, the suite size, the budget, and how many tests touched the changed file.
2. **Scores** shows the duration, priority, history, failure chance, and value used for that run.
3. **Methods** shows what retest-all, random, coverage, history, ML ranking, greedy, ALNS, and ALNS-RL kept.
4. **Test results** shows the pass or fail result of the tests that command actually ran.
5. **Q-table** shows the moves learned during that search.

You can still run `adaptive-ci demo` in the terminal. Then press **Refresh from last command** so the page shows that run.

**Simulation** is the other button in the header. Open it when you want a made-up series of many builds. Its own tabs are Comparison, Learning curves, Q-learning brain, and Test suite. Those numbers are not the shop run. Say that when you present them.

The old shop page recalculated the tables itself and showed a fixed diff. That is no longer what Shop run does.

## Run selection on your own change

`adaptive-ci select` does need Git history, because it diffs two commits. You can also pass the changed file yourself:

```bash
adaptive-ci select --changed path/to/file.py --budget 60
adaptive-ci run
```

`--budget` is in seconds. Results go to `.adaptive-ci/plan.json`, `.adaptive-ci/results.json`, and `.adaptive-ci/history.db`.

To compare one change by hand:

```bash
adaptive-ci select --changed path/to/file.py --budget 60 --algorithm greedy
adaptive-ci select --changed path/to/file.py --budget 60 --algorithm alns
adaptive-ci select --changed path/to/file.py --budget 60 --algorithm alns-rl
```

Each test in the manifest needs a `covers` list. A test without one cannot be matched to a changed file. `adaptive-ci discover-pytest` creates a manifest, but it leaves `covers` empty, so you must fill those paths before selection is meaningful.

## Current limits

- Coverage is path-level and written in the manifest. It is not collected automatically.
- Test priority is an input. A failure does not change it yet.
- Tests run one at a time.
- On the shop demo, ALNS-RL does not beat greedy.
- The browser replay uses generated builds, not a real CI history.
- The GitHub Actions workflow is included, but it is not part of the local demo.

## Development

```bash
ruff check .
pytest
```
