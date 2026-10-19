from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .alns import ACTIONS

POLICY_VERSION = 1


def load_policy(path: str | Path) -> dict[str, list[float]]:
    target = Path(path)
    if not target.exists():
        return {}
    payload = json.loads(target.read_text())
    if payload.get("version") != POLICY_VERSION:
        raise ValueError(f"unsupported policy version in {target}")
    if payload.get("action_count") != len(ACTIONS):
        raise ValueError(f"incompatible action count in {target}")
    table = payload.get("q_table")
    if not isinstance(table, dict):
        raise TypeError(f"invalid Q-table in {target}")
    return {str(state): [float(value) for value in values] for state, values in table.items()}


def save_policy(path: str | Path, q_table: dict[str, list[float]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": POLICY_VERSION,
        "action_count": len(ACTIONS),
        "q_table": q_table,
    }
    descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, target)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
