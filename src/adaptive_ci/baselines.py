from __future__ import annotations

import random

from .models import ScoredTest


def _pack(order: list[ScoredTest], budget: float) -> list[ScoredTest]:
    selected: list[ScoredTest] = []
    used = 0.0
    for item in order:
        if used + item.effective_duration <= budget + 1e-9:
            selected.append(item)
            used += item.effective_duration
    return selected


def select_random(scored: list[ScoredTest], budget: float, seed: int) -> list[ScoredTest]:
    order = list(scored)
    random.Random(seed).shuffle(order)
    return _pack(order, budget)


def select_coverage(scored: list[ScoredTest], budget: float) -> list[ScoredTest]:
    order = sorted(
        scored,
        key=lambda item: (item.relevance, len(item.test.covers), item.effective_duration),
        reverse=True,
    )
    return _pack(order, budget)


def select_history(scored: list[ScoredTest], budget: float) -> list[ScoredTest]:
    order = sorted(scored, key=lambda item: (item.failure_ema, item.probability), reverse=True)
    return _pack(order, budget)


def select_ml_rank(scored: list[ScoredTest], budget: float) -> list[ScoredTest]:
    order = sorted(scored, key=lambda item: (item.probability, item.base_value), reverse=True)
    return _pack(order, budget)
