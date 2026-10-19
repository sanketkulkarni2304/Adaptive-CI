import random

from adaptive_ci.alns import (
    DESTROY_OPERATORS,
    DESTRUCTION_LEVELS,
    REPAIR_OPERATORS,
    _destroy,
    _repair,
    alns_search,
    greedy_solution,
    solution_cost,
)
from adaptive_ci.models import ScoredTest
from adaptive_ci.models import TestSpec as Spec
from adaptive_ci.policy import load_policy, save_policy


def scored_tests():
    return [
        ScoredTest(
            Spec(
                f"test-{index}",
                ["synthetic"],
                duration_seconds=float(2 + index % 4),
                covers=(f"src/{index % 5}.py", f"src/{(index + 1) % 5}.py"),
                priority=0.5,
                always_run=index == 0,
            ),
            probability=0.05 + index * 0.03,
            relevance=0.5,
            base_value=0.2 + index * 0.05,
            effective_duration=float(2 + index % 4),
            history_staleness=index / 10,
        )
        for index in range(10)
    ]


def test_alns_rl_is_feasible_preserves_mandatory_and_updates_q_values():
    tests = scored_tests()
    q_table = {}

    result = alns_search(tests, 15, iterations=80, seed=7, q_table=q_table)

    assert solution_cost({tests.index(item) for item in result.selected}, tests) <= 15
    assert tests[0] in result.selected
    assert result.q_updates == 80
    assert any(value != 0 for values in q_table.values() for value in values)


def test_seeded_alns_is_deterministic():
    tests = scored_tests()
    first_q, second_q = {}, {}

    first = alns_search(tests, 15, iterations=50, seed=11, q_table=first_q)
    second = alns_search(tests, 15, iterations=50, seed=11, q_table=second_q)

    assert [item.test.id for item in first.selected] == [
        item.test.id for item in second.selected
    ]
    assert first.objective == second.objective
    assert first_q == second_q


def test_every_destroy_repair_and_level_combination_stays_feasible():
    tests = scored_tests()
    initial = greedy_solution(tests, 15)
    for destroy in DESTROY_OPERATORS:
        for repair in REPAIR_OPERATORS:
            for level in DESTRUCTION_LEVELS:
                rng = random.Random(3)
                candidate = _repair(
                    _destroy(initial, tests, destroy, level, rng),
                    tests,
                    15,
                    repair,
                    rng,
                )
                assert solution_cost(candidate, tests) <= 15
                assert 0 in candidate


def test_policy_round_trip(tmp_path):
    path = tmp_path / "qtable.json"
    table = {"0:0:0": [float(index) for index in range(60)]}

    save_policy(path, table)

    assert load_policy(path) == table
