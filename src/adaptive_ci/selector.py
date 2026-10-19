from __future__ import annotations

from datetime import datetime, timezone

from .alns import alns_search, greedy_solution, solution_objective
from .models import Plan, ScoredTest


def select_tests(
    scored: list[ScoredTest],
    changed_paths: list[str],
    budget_seconds: float,
    overhead_seconds: float = 0.0,
    *,
    algorithm: str = "greedy",
    iterations: int = 500,
    seed: int = 42,
    q_table: dict[str, list[float]] | None = None,
) -> Plan:
    available = budget_seconds - overhead_seconds
    if available <= 0:
        raise ValueError("budget must be greater than reserved selection overhead")
    if algorithm == "greedy":
        indices = greedy_solution(scored, available)
        selected = sorted(
            (scored[index] for index in indices),
            key=lambda item: item.base_value / item.effective_duration,
            reverse=True,
        )
        objective = solution_objective(indices, scored)
        search = {"objective": round(objective, 6), "iterations": 0}
    elif algorithm in {"alns", "alns-rl"}:
        result = alns_search(
            scored,
            available,
            iterations=iterations,
            seed=seed,
            use_rl=algorithm == "alns-rl",
            q_table=q_table,
        )
        selected = result.selected
        search = {
            "objective": round(result.objective, 6),
            "iterations": result.iterations,
            "accepted_moves": result.accepted_moves,
            "improvements": result.improvements,
            "q_updates": result.q_updates,
            "operator_counts": result.operator_counts,
        }
    else:
        raise ValueError(f"unknown selection algorithm: {algorithm}")
    used = sum(item.effective_duration for item in selected)

    entries = [
        {
            "id": item.test.id,
            "command": item.test.command,
            "estimated_duration_seconds": round(item.effective_duration, 3),
            "failure_probability": round(item.probability, 4),
            "relevance": round(item.relevance, 4),
            "value": round(item.base_value, 4),
        }
        for item in selected
    ]
    return Plan(
        budget_seconds=budget_seconds,
        changed_paths=changed_paths,
        selected=entries,
        estimated_duration_seconds=round(used + overhead_seconds, 3),
        generated_at=datetime.now(timezone.utc).isoformat(),
        selector=f"{algorithm}-v1",
        search=search,
    )
