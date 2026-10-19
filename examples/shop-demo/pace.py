import json
import time
from pathlib import Path

DURATIONS = {
    item["id"]: float(item["duration_seconds"])
    for item in json.loads((Path(__file__).parent / "tests.json").read_text())["tests"]
}


def pace(test_id: str) -> None:
    time.sleep(DURATIONS[test_id])
