import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Literal

StatusValue = Literal[
    "operational",
    "degraded_performance",
    "partial_outage",
    "major_outage",
    "unknown",
]

HISTORY_DIR = Path.home() / ".local" / "share" / "claude-status"
HISTORY_FILE = HISTORY_DIR / "history.json"


@dataclass
class PollRecord:
    ts: int
    claude_code: StatusValue
    claude_api: StatusValue


def load_history() -> list[PollRecord]:
    if not HISTORY_FILE.exists():
        return []
    records: list[PollRecord] = []
    try:
        with open(HISTORY_FILE) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    records.append(PollRecord(**d))
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue
    except OSError:
        return []
    return records


def append_record(record: PollRecord) -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, "a") as f:
        f.write(json.dumps(asdict(record)) + "\n")
