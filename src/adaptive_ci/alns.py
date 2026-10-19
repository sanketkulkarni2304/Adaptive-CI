from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from itertools import product

from .models import ScoredTest

DESTROY_OPERATORS = ("random", "worst-density", "redundancy", "long", "stale-history")
REPAIR_OPERATORS = ("greedy-density", "coverage-gap", "failure-first", "randomized-greedy")
DESTRUCTION_LEVELS = (0.1, 0.2, 0.3)
ACTIONS = tuple(product(DESTROY_OPERATORS, REPAIR_OPERATORS, DESTRUCTION_LEVELS))


@dataclass
class SearchResult:
    selected: list[ScoredTest]
    objective: float
    iterations: int
    accepted_moves: int = 0
    improvements: int = 0
    q_updates: int = 0
    operator_counts: dict[str, int] = field(default_factory=dict)


def solution_cost(indices: set[int], tests: list[ScoredTest]) -> float:
    return sum(tests[index].effective_duration for index in indices)


def solution_objective(
    indices: set[int],
    tests: list[ScoredTest],
    coverage_weight: float = 0.25,
) -> float:
    value = sum(tests[index].base_value for index in indices)
    universe = {unit for item in tests for unit in item.test.covers}
    covered = {unit for index in indices for unit in tests[index].test.covers}
    return value + coverage_weight * len(covered) / max(1, len(universe))


def _marginal_value(index: int, selected: set[int], tests: list[ScoredTest]) -> float:
    covered = {unit for chosen in selected for unit in tests[chosen].test.covers}
    units = set(tests[index].test.covers)
    coverage_gain = len(units - covered) / max(1, len(units))
    return tests[index].base_value + 0.25 * coverage_gain


def _repair(
    selected: set[int],
    tests: list[ScoredTest],
    budget: float,
    operator: str,
    rng: random.Random,
) -> set[int]:
    result = set(selected)
    while True:
        candidates = [
            index
            for index in range(len(tests))
            if index not in result
            and solution_cost(result, tests) + tests[index].effective_duration <= budget
        ]
        if not candidates:
            return result
        if operator == "greedy-density":
            chosen = max(
                candidates,
                key=lambda i: _marginal_value(i, result, tests)
                / tests[i].effective_duration**0.75,
            )
        elif operator == "coverage-gap":
            covered = {unit for i in result for unit in tests[i].test.covers}
            chosen = max(
                candidates,
                key=lambda i: (
                    len(set(tests[i].test.covers) - covered),
                    _marginal_value(i, result, tests) / tests[i].effective_duration,
                ),
            )
        elif operator == "failure-first":
            chosen = max(
                candidates,
                key=lambda i: (
                    tests[i].probability,
                    _marginal_value(i, result, tests) / tests[i].effective_duration,
                ),
            )
        elif operator == "randomized-greedy":
            chosen = max(
                candidates,
                key=lambda i: _marginal_value(i, result, tests)
                / tests[i].effective_duration
                * rng.uniform(0.75, 1.25),
            )
        else:
            raise ValueError(f"unknown repair operator: {operator}")
        result.add(chosen)


def greedy_solution(tests: list[ScoredTest], budget: float) -> set[int]:
    mandatory = {index for index, item in enumerate(tests) if item.test.always_run}
    if solution_cost(mandatory, tests) > budget:
        raise ValueError("always-run tests exceed the available test budget")
    return _repair(mandatory, tests, budget, "greedy-density", random.Random(0))


def _destroy(
    selected: set[int],
    tests: list[ScoredTest],
    operator: str,
    level: float,
    rng: random.Random,
) -> set[int]:
    removable = [index for index in selected if not tests[index].test.always_run]
    if not removable:
        return set(selected)
    count = min(len(removable), max(1, round(len(removable) * level)))
    if operator == "random":
        removed = rng.sample(removable, count)
    elif operator == "worst-density":
        removed = sorted(
            removable,
            key=lambda i: tests[i].base_value / tests[i].effective_duration,
        )[:count]
    elif operator == "redundancy":
        frequencies: dict[str, int] = {}
        for index in selected:
            for unit in tests[index].test.covers:
                frequencies[unit] = frequencies.get(unit, 0) + 1
        removed = sorted(
            removable,
            key=lambda i: (
                sum(frequencies[unit] == 1 for unit in tests[i].test.covers),
                tests[i].base_value,
            ),
        )[:count]
    elif operator == "long":
        removed = sorted(
            removable, key=lambda i: tests[i].effective_duration, reverse=True
        )[:count]
    elif operator == "stale-history":
        removed = sorted(
            removable,
            key=lambda i: (tests[i].history_staleness, -tests[i].probability),
            reverse=True,
        )[:count]
    else:
        raise ValueError(f"unknown destroy operator: {operator}")
    return selected - set(removed)


def _state(
    current: set[int],
    best_score: float,
    current_score: float,
    tests: list[ScoredTest],
    budget: float,
    stagnation: int,
) -> str:
    slack = max(0.0, budget - solution_cost(current, tests)) / max(budget, 0.01)
    slack_bin = 0 if slack < 0.1 else 1 if slack < 0.3 else 2
    stagnation_bin = 0 if stagnation < 5 else 1 if stagnation < 20 else 2
    gap = max(0.0, best_score - current_score) / max(abs(best_score), 0.01)
    gap_bin = 0 if gap < 0.01 else 1 if gap < 0.1 else 2
    return f"{slack_bin}:{stagnation_bin}:{gap_bin}"


def _q_values(q_table: dict[str, list[float]], state: str) -> list[float]:
    values = q_table.setdefault(state, [0.0] * len(ACTIONS))
    if len(values) != len(ACTIONS):
        raise ValueError("Q-table action count is incompatible with this version")
    return values


def alns_search(
    tests: list[ScoredTest],
    budget: float,
    *,
    iterations: int = 500,
    seed: int = 42,
    use_rl: bool = True,
    q_table: dict[str, list[float]] | None = None,
    alpha: float = 0.1,
    gamma: float = 0.9,
    epsilon_start: float = 0.3,
    epsilon_end: float = 0.05,
) -> SearchResult:
    if iterations < 1:
        raise ValueError("iterations must be positive")
    rng = random.Random(seed)
    q_table = q_table if q_table is not None else {}
    current = greedy_solution(tests, budget)
    current_score = solution_objective(current, tests)
    best, best_score = set(current), current_score
    temperature = max(0.01, abs(current_score) * 0.1)
    stagnation = accepted = improvements = q_updates = 0
    operator_counts: dict[str, int] = {}

    for iteration in range(iterations):
        state = _state(current, best_score, current_score, tests, budget, stagnation)
        epsilon = epsilon_start + (epsilon_end - epsilon_start) * iteration / iterations
        values = _q_values(q_table, state)
        if not use_rl or rng.random() < epsilon:
            action_index = rng.randrange(len(ACTIONS))
        else:
            maximum = max(values)
            ties = [index for index, value in enumerate(values) if value == maximum]
            action_index = rng.choice(ties)
        destroy, repair, level = ACTIONS[action_index]
        operator_key = f"{destroy}+{repair}+{level:.1f}"
        operator_counts[operator_key] = operator_counts.get(operator_key, 0) + 1

        candidate = _repair(
            _destroy(current, tests, destroy, level, rng), tests, budget, repair, rng
        )
        candidate_score = solution_objective(candidate, tests)
        previous_score = current_score
        improved_current = candidate_score > previous_score + 1e-12
        new_global = candidate_score > best_score + 1e-12
        accept = improved_current or rng.random() < math.exp(
            min(0.0, (candidate_score - previous_score) / max(temperature, 1e-9))
        )
        reward = 0.0
        if accept:
            current, current_score = candidate, candidate_score
            accepted += 1
            reward = 2.0 if improved_current else 1.0
        if new_global:
            best, best_score = set(candidate), candidate_score
            improvements += 1
            stagnation = 0
            reward = 3.0
        else:
            stagnation += 1

        if use_rl:
            next_state = _state(current, best_score, current_score, tests, budget, stagnation)
            target = reward + gamma * max(_q_values(q_table, next_state))
            values[action_index] += alpha * (target - values[action_index])
            q_updates += 1
        temperature *= 0.995

    ordered = sorted(
        best,
        key=lambda i: tests[i].base_value / tests[i].effective_duration,
        reverse=True,
    )
    return SearchResult(
        [tests[index] for index in ordered],
        best_score,
        iterations,
        accepted,
        improvements,
        q_updates,
        operator_counts,
    )
