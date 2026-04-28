# Claude Status TUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python/Textual TUI that polls the Claude statuspage API every 60s, displays a session-accumulated bar chart + current status badge for Claude Code and Claude API, shows active incident banners, and fires cmux notifications on status changes.

**Architecture:** Four focused modules (`history`, `poller`, `notifier`, `app`) keep data persistence, API fetching, alerting, and UI strictly separated. The Textual app wires them together: on mount it loads persisted history, immediately polls, then polls every 60s via a thread worker. Each poll result is appended to an NDJSON file so history survives restarts.

**Tech Stack:** Python 3.12, Textual 8.2.3, pytest, stdlib only for HTTP (`urllib.request`)

---

## File Structure

```
~/mjs/claude-status/
├── claude_status.py          # entry point: #!/usr/bin/env python3.12
├── app.py                    # Textual App + all widgets
├── poller.py                 # API fetch + data structures
├── history.py                # PollRecord dataclass + NDJSON persistence
├── notifier.py               # cmux notify + transition detection
├── requirements.txt          # textual==8.2.3
├── tests/
│   ├── __init__.py
│   ├── test_history.py
│   ├── test_poller.py
│   ├── test_notifier.py
│   └── test_app_logic.py
└── docs/
    └── superpowers/
        ├── specs/2026-04-15-claude-status-tui-design.md
        └── plans/2026-04-15-claude-status-tui.md
```

**Responsibility of each file:**
- `history.py` — `PollRecord` dataclass, `StatusValue` type, `load_history()`, `append_record()`. Zero UI, zero network.
- `poller.py` — `Incident` dataclass, `FetchResult` dataclass, `fetch_status()`. Zero UI, zero disk I/O.
- `notifier.py` — `detect_transition()`, `notify_cmux()`, `check_and_notify()`. Zero UI, zero network.
- `app.py` — `ComponentRow`, `IncidentBanner`, `StatusFooter`, `ClaudeStatusApp`. Imports all three modules, owns the poll loop and UI state.
- `claude_status.py` — one line: `ClaudeStatusApp().run()`.

---

## Task 1: Project Setup

**Files:**
- Create: `requirements.txt`
- Create: `tests/__init__.py`
- Create: `pytest.ini`

- [ ] **Step 1: Write requirements.txt**

```
textual==8.2.3
pytest==8.3.5
```

- [ ] **Step 2: Write pytest.ini**

```ini
[pytest]
testpaths = tests
```

- [ ] **Step 3: Create tests/__init__.py**

```python
```

(Empty file — makes `tests/` a package so imports resolve correctly.)

- [ ] **Step 4: Install dependencies**

Run:
```bash
pip3.12 install textual==8.2.3 pytest==8.3.5
```

Expected: both packages install without error.

- [ ] **Step 5: Verify Python and Textual available**

Run:
```bash
python3.12 -c "import textual; print(textual.__version__)"
```

Expected: `8.2.3`

- [ ] **Step 6: Commit**

```bash
cd ~/mjs/claude-status
git add requirements.txt pytest.ini tests/__init__.py
git commit -m "chore: project setup, deps, pytest config"
```

---

## Task 2: History Module

**Files:**
- Create: `history.py`
- Create: `tests/test_history.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_history.py`:

```python
import json
import pytest
from pathlib import Path
from unittest.mock import patch
from history import PollRecord, load_history, append_record


def test_load_history_returns_empty_when_file_missing(tmp_path):
    with patch("history.HISTORY_FILE", tmp_path / "history.json"), \
         patch("history.HISTORY_DIR", tmp_path):
        assert load_history() == []


def test_append_and_load_round_trips(tmp_path):
    record = PollRecord(ts=1713196800, claude_code="operational", claude_api="operational")
    with patch("history.HISTORY_FILE", tmp_path / "history.json"), \
         patch("history.HISTORY_DIR", tmp_path):
        append_record(record)
        loaded = load_history()
    assert loaded == [record]


def test_load_history_multiple_records(tmp_path):
    test_file = tmp_path / "history.json"
    test_file.write_text(
        '{"ts": 1713196800, "claude_code": "operational", "claude_api": "operational"}\n'
        '{"ts": 1713196860, "claude_code": "degraded_performance", "claude_api": "operational"}\n'
    )
    with patch("history.HISTORY_FILE", test_file):
        loaded = load_history()
    assert len(loaded) == 2
    assert loaded[0] == PollRecord(ts=1713196800, claude_code="operational", claude_api="operational")
    assert loaded[1] == PollRecord(ts=1713196860, claude_code="degraded_performance", claude_api="operational")


def test_load_history_corrupt_file_returns_empty(tmp_path):
    test_file = tmp_path / "history.json"
    test_file.write_text("not valid json\n")
    with patch("history.HISTORY_FILE", test_file):
        assert load_history() == []


def test_append_creates_directory_if_missing(tmp_path):
    data_dir = tmp_path / "nested" / "dir"
    data_file = data_dir / "history.json"
    record = PollRecord(ts=1, claude_code="operational", claude_api="operational")
    with patch("history.HISTORY_FILE", data_file), \
         patch("history.HISTORY_DIR", data_dir):
        append_record(record)
    assert data_file.exists()
```

- [ ] **Step 2: Run to confirm they all fail**

```bash
cd ~/mjs/claude-status
python3.12 -m pytest tests/test_history.py -v
```

Expected: `ModuleNotFoundError: No module named 'history'`

- [ ] **Step 3: Write history.py**

Create `history.py`:

```python
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
    claude_code: str
    claude_api: str


def load_history() -> list[PollRecord]:
    if not HISTORY_FILE.exists():
        return []
    records: list[PollRecord] = []
    try:
        with open(HISTORY_FILE) as f:
            for line in f:
                line = line.strip()
                if line:
                    d = json.loads(line)
                    records.append(PollRecord(**d))
    except (json.JSONDecodeError, KeyError, TypeError):
        return []
    return records


def append_record(record: PollRecord) -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, "a") as f:
        f.write(json.dumps(asdict(record)) + "\n")
```

- [ ] **Step 4: Run tests and confirm they pass**

```bash
python3.12 -m pytest tests/test_history.py -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add history.py tests/test_history.py
git commit -m "feat: history module — PollRecord, load/append NDJSON"
```

---

## Task 3: Poller Module

**Files:**
- Create: `poller.py`
- Create: `tests/test_poller.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_poller.py`:

```python
import json
import urllib.error
import pytest
from unittest.mock import MagicMock, patch
from poller import fetch_status, CLAUDE_CODE_ID, CLAUDE_API_ID, FetchResult


MOCK_COMPONENTS = {
    "components": [
        {"id": CLAUDE_CODE_ID, "name": "Claude Code", "status": "operational"},
        {"id": CLAUDE_API_ID, "name": "Claude API (api.anthropic.com)", "status": "degraded_performance"},
        {"id": "other-id", "name": "claude.ai", "status": "operational"},
    ]
}

MOCK_INCIDENTS_EMPTY = {"incidents": []}

MOCK_INCIDENTS = {
    "incidents": [
        {
            "id": "abc123",
            "name": "Elevated errors on Claude Code",
            "status": "identified",
            "created_at": "2026-04-15T14:53:02.000Z",
            "impact": "critical",
        }
    ]
}


def _make_response(data: dict) -> MagicMock:
    mock = MagicMock()
    mock.read.return_value = json.dumps(data).encode()
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    return mock


def _make_urlopen(responses: list) -> callable:
    it = iter(responses)
    return lambda url, timeout: next(it)


def test_fetch_status_parses_claude_code_and_api(monkeypatch):
    monkeypatch.setattr(
        "poller.urllib.request.urlopen",
        _make_urlopen([_make_response(MOCK_COMPONENTS), _make_response(MOCK_INCIDENTS_EMPTY)]),
    )
    result = fetch_status()
    assert result.error is None
    assert result.record.claude_code == "operational"
    assert result.record.claude_api == "degraded_performance"
    assert result.incidents == []


def test_fetch_status_parses_incidents(monkeypatch):
    monkeypatch.setattr(
        "poller.urllib.request.urlopen",
        _make_urlopen([_make_response(MOCK_COMPONENTS), _make_response(MOCK_INCIDENTS)]),
    )
    result = fetch_status()
    assert len(result.incidents) == 1
    assert result.incidents[0].name == "Elevated errors on Claude Code"
    assert result.incidents[0].status == "identified"
    assert result.incidents[0].impact == "critical"


def test_fetch_status_network_error_returns_error(monkeypatch):
    monkeypatch.setattr(
        "poller.urllib.request.urlopen",
        lambda url, timeout: (_ for _ in ()).throw(urllib.error.URLError("connection refused")),
    )
    result = fetch_status()
    assert result.error is not None
    assert result.record is None
    assert result.incidents == []


def test_fetch_status_missing_component_returns_unknown(monkeypatch):
    components_without_code = {"components": [
        {"id": CLAUDE_API_ID, "name": "Claude API", "status": "operational"},
    ]}
    monkeypatch.setattr(
        "poller.urllib.request.urlopen",
        _make_urlopen([_make_response(components_without_code), _make_response(MOCK_INCIDENTS_EMPTY)]),
    )
    result = fetch_status()
    assert result.record.claude_code == "unknown"
    assert result.record.claude_api == "operational"


def test_fetch_status_records_timestamp(monkeypatch):
    monkeypatch.setattr(
        "poller.urllib.request.urlopen",
        _make_urlopen([_make_response(MOCK_COMPONENTS), _make_response(MOCK_INCIDENTS_EMPTY)]),
    )
    import time
    before = int(time.time())
    result = fetch_status()
    after = int(time.time())
    assert before <= result.record.ts <= after
```

- [ ] **Step 2: Run to confirm they all fail**

```bash
python3.12 -m pytest tests/test_poller.py -v
```

Expected: `ModuleNotFoundError: No module named 'poller'`

- [ ] **Step 3: Write poller.py**

Create `poller.py`:

```python
import json
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field

from history import PollRecord

COMPONENTS_URL = "https://status.claude.com/api/v2/components.json"
INCIDENTS_URL = "https://status.claude.com/api/v2/incidents/unresolved.json"

CLAUDE_CODE_ID = "yyzkbfz2thpt"
CLAUDE_API_ID = "k8w3r06qmzrp"


@dataclass
class Incident:
    name: str
    status: str
    created_at: str
    impact: str


@dataclass
class FetchResult:
    record: PollRecord | None
    incidents: list[Incident] = field(default_factory=list)
    error: str | None = None


def _fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read())


def fetch_status() -> FetchResult:
    try:
        components_data = _fetch_json(COMPONENTS_URL)
        by_id = {c["id"]: c["status"] for c in components_data["components"]}

        record = PollRecord(
            ts=int(time.time()),
            claude_code=by_id.get(CLAUDE_CODE_ID, "unknown"),
            claude_api=by_id.get(CLAUDE_API_ID, "unknown"),
        )

        incidents_data = _fetch_json(INCIDENTS_URL)
        incidents = [
            Incident(
                name=i["name"],
                status=i["status"],
                created_at=i["created_at"],
                impact=i["impact"],
            )
            for i in incidents_data.get("incidents", [])
        ]

        return FetchResult(record=record, incidents=incidents)

    except Exception as exc:
        return FetchResult(record=None, error=str(exc))
```

- [ ] **Step 4: Run tests and confirm they pass**

```bash
python3.12 -m pytest tests/test_poller.py -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add poller.py tests/test_poller.py
git commit -m "feat: poller module — fetch_status with Incident/FetchResult"
```

---

## Task 4: Notifier Module

**Files:**
- Create: `notifier.py`
- Create: `tests/test_notifier.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_notifier.py`:

```python
import os
import pytest
from unittest.mock import patch, call
from notifier import detect_transition, notify_cmux, check_and_notify


def test_detect_degraded():
    assert detect_transition("operational", "degraded_performance") == "degraded"


def test_detect_outage():
    assert detect_transition("operational", "partial_outage") == "degraded"


def test_detect_major_outage():
    assert detect_transition("operational", "major_outage") == "degraded"


def test_detect_recovered():
    assert detect_transition("degraded_performance", "operational") == "recovered"


def test_detect_no_change_operational():
    assert detect_transition("operational", "operational") is None


def test_detect_no_change_degraded():
    assert detect_transition("degraded_performance", "partial_outage") is None


def test_notify_skipped_when_not_in_cmux():
    with patch.dict(os.environ, {}, clear=True):
        with patch("notifier.subprocess.run") as mock_run:
            notify_cmux("title", "body")
    mock_run.assert_not_called()


def test_notify_fires_when_in_cmux():
    with patch.dict(os.environ, {"CMUX_WORKSPACE_ID": "workspace:1"}):
        with patch("notifier.subprocess.run") as mock_run:
            notify_cmux("Claude Code degraded", "Degraded Performance")
    mock_run.assert_called_once_with(
        ["cmux", "notify", "--title", "Claude Code degraded", "--body", "Degraded Performance"],
        capture_output=True,
    )


def test_check_and_notify_fires_on_degradation():
    with patch.dict(os.environ, {"CMUX_WORKSPACE_ID": "workspace:1"}):
        with patch("notifier.subprocess.run") as mock_run:
            check_and_notify("Claude Code", "operational", "degraded_performance")
    args = mock_run.call_args[0][0]
    assert "Claude Code degraded" in args


def test_check_and_notify_fires_on_recovery():
    with patch.dict(os.environ, {"CMUX_WORKSPACE_ID": "workspace:1"}):
        with patch("notifier.subprocess.run") as mock_run:
            check_and_notify("Claude Code", "degraded_performance", "operational")
    args = mock_run.call_args[0][0]
    assert "Claude Code recovered" in args


def test_check_and_notify_silent_on_no_change():
    with patch.dict(os.environ, {"CMUX_WORKSPACE_ID": "workspace:1"}):
        with patch("notifier.subprocess.run") as mock_run:
            check_and_notify("Claude Code", "operational", "operational")
    mock_run.assert_not_called()
```

- [ ] **Step 2: Run to confirm they all fail**

```bash
python3.12 -m pytest tests/test_notifier.py -v
```

Expected: `ModuleNotFoundError: No module named 'notifier'`

- [ ] **Step 3: Write notifier.py**

Create `notifier.py`:

```python
import os
import subprocess


def detect_transition(old: str, new: str) -> str | None:
    """Returns 'degraded', 'recovered', or None."""
    was_ok = old == "operational"
    is_ok = new == "operational"
    if was_ok and not is_ok:
        return "degraded"
    if not was_ok and is_ok:
        return "recovered"
    return None


def notify_cmux(title: str, body: str) -> None:
    if not os.environ.get("CMUX_WORKSPACE_ID"):
        return
    subprocess.run(
        ["cmux", "notify", "--title", title, "--body", body],
        capture_output=True,
    )


def check_and_notify(component_name: str, old_status: str, new_status: str) -> None:
    transition = detect_transition(old_status, new_status)
    if transition == "degraded":
        label = new_status.replace("_", " ").title()
        notify_cmux(f"{component_name} degraded", label)
    elif transition == "recovered":
        notify_cmux(f"{component_name} recovered", "Back to operational")
```

- [ ] **Step 4: Run tests and confirm they pass**

```bash
python3.12 -m pytest tests/test_notifier.py -v
```

Expected: 10 tests pass.

- [ ] **Step 5: Commit**

```bash
git add notifier.py tests/test_notifier.py
git commit -m "feat: notifier module — transition detection + cmux notify"
```

---

## Task 5: App Logic (Pure Functions)

**Files:**
- Create: `tests/test_app_logic.py`
- Create: `app.py` (logic functions only — no Textual imports yet)

These functions are pure and fast to test without spinning up a Textual app.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_app_logic.py`:

```python
from history import PollRecord
from app import render_bar, uptime_percent


def _op(ts: int) -> PollRecord:
    return PollRecord(ts=ts, claude_code="operational", claude_api="operational")


def _deg(ts: int) -> PollRecord:
    return PollRecord(ts=ts, claude_code="degraded_performance", claude_api="operational")


def test_uptime_100_percent():
    history = [_op(i) for i in range(10)]
    assert uptime_percent(history, "claude_code") == 100.0


def test_uptime_50_percent():
    history = [_op(1), _deg(2)]
    assert uptime_percent(history, "claude_code") == 50.0


def test_uptime_empty_history():
    assert uptime_percent([], "claude_code") == 0.0


def test_render_bar_operational_uses_green():
    bar = render_bar([_op(1)], "claude_code", width=10)
    assert "green" in bar
    assert "█" in bar


def test_render_bar_degraded_uses_orange():
    bar = render_bar([_deg(1)], "claude_code", width=10)
    assert "orange3" in bar


def test_render_bar_truncates_to_width():
    history = [_op(i) for i in range(20)]
    bar = render_bar(history, "claude_code", width=5)
    # Rich markup wraps each char; count raw block chars
    assert bar.count("█") == 5


def test_render_bar_shows_all_when_fewer_than_width():
    history = [_op(i) for i in range(3)]
    bar = render_bar(history, "claude_code", width=10)
    assert bar.count("█") == 3


def test_render_bar_unknown_uses_dim_block():
    record = PollRecord(ts=1, claude_code="unknown", claude_api="operational")
    bar = render_bar([record], "claude_code", width=10)
    assert "░" in bar
    assert "dim" in bar
```

- [ ] **Step 2: Run to confirm they fail**

```bash
python3.12 -m pytest tests/test_app_logic.py -v
```

Expected: `ModuleNotFoundError: No module named 'app'`

- [ ] **Step 3: Write app.py with just the logic functions**

Create `app.py`:

```python
import os
import subprocess
from datetime import datetime, timezone

from textual.app import App, ComposeResult
from textual.widgets import Static
from textual import work

from history import PollRecord, load_history, append_record
from poller import fetch_status, Incident
from notifier import check_and_notify

POLL_INTERVAL = 60

_STATUS_COLORS = {
    "operational": "green",
    "degraded_performance": "orange3",
    "partial_outage": "red",
    "major_outage": "bold red",
    "unknown": "dim",
}

_STATUS_LABELS = {
    "operational": "Operational",
    "degraded_performance": "Degraded Performance",
    "partial_outage": "Partial Outage",
    "major_outage": "Major Outage",
    "unknown": "Unknown",
}

_BAR_CHARS: dict[str, tuple[str, str]] = {
    "operational": ("█", "green"),
    "degraded_performance": ("█", "orange3"),
    "partial_outage": ("█", "red"),
    "major_outage": ("█", "bold red"),
    "unknown": ("░", "dim"),
}


def uptime_percent(history: list[PollRecord], field: str) -> float:
    if not history:
        return 0.0
    operational = sum(1 for r in history if getattr(r, field) == "operational")
    return (operational / len(history)) * 100.0


def render_bar(history: list[PollRecord], field: str, width: int) -> str:
    records = history[-width:] if len(history) > width else history
    parts = []
    for r in records:
        status = getattr(r, field)
        char, color = _BAR_CHARS.get(status, ("░", "dim"))
        parts.append(f"[{color}]{char}[/{color}]")
    return "".join(parts)


def _format_age(created_at: str) -> str:
    try:
        ts = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        delta = int((datetime.now(timezone.utc) - ts).total_seconds())
        if delta < 60:
            return f"{delta}s ago"
        elif delta < 3600:
            return f"{delta // 60} min ago"
        else:
            return f"{delta // 3600} hr ago"
    except Exception:
        return "unknown age"


class ComponentRow(Static):
    def __init__(self, label: str, field: str, **kwargs) -> None:
        super().__init__("Loading...", **kwargs)
        self._label = label
        self._field = field
        self._history: list[PollRecord] = []
        self._current_status: str = "unknown"

    def update_data(self, history: list[PollRecord], current_status: str) -> None:
        self._history = history
        self._current_status = current_status
        self._redraw()

    def _redraw(self) -> None:
        width = os.get_terminal_size(fallback=(80, 24)).columns - 4
        color = _STATUS_COLORS.get(self._current_status, "dim")
        label_str = _STATUS_LABELS.get(self._current_status, "Unknown")
        pct = uptime_percent(self._history, self._field)
        bars = render_bar(self._history, self._field, width)

        badge = f"[{color}]● {label_str}[/{color}]"
        padding = max(1, width - len(self._label) - len(label_str) - 3)
        top = f"[bold]{self._label}[/bold]{' ' * padding}{badge}"

        dash = max(1, (width - 22) // 2)
        footer = f"[dim]Session start {'─' * dash} {pct:.1f}% uptime {'─' * dash} Now[/dim]"

        self.update(f"{top}\n{bars}\n{footer}")


class IncidentBanner(Static):
    def __init__(self, **kwargs) -> None:
        super().__init__("", **kwargs)

    def update_incidents(self, incidents: list[Incident]) -> None:
        if not incidents:
            self.update("")
            self.add_class("hidden")
            return
        self.remove_class("hidden")
        lines = []
        for incident in incidents:
            age = _format_age(incident.created_at)
            lines.append(f"[yellow]⚠[/yellow] [bold]{incident.name}[/bold]")
            lines.append(f"  [dim]{incident.status.capitalize()} · {age}[/dim]")
        self.update("\n".join(lines))


class StatusFooter(Static):
    def __init__(self, **kwargs) -> None:
        super().__init__("Initializing...", **kwargs)
        self._last_updated: str = "—"
        self._next_poll: int = POLL_INTERVAL
        self._error: str | None = None

    def on_mount(self) -> None:
        self.set_interval(1, self._tick)

    def _tick(self) -> None:
        if self._next_poll > 0:
            self._next_poll -= 1
        self._redraw()

    def mark_polled(self, error: str | None = None) -> None:
        self._last_updated = datetime.now().strftime("%H:%M:%S")
        self._next_poll = POLL_INTERVAL
        self._error = error
        self._redraw()

    def _redraw(self) -> None:
        if self._error:
            status = f"[red]Fetch failed: {self._error[:50]}[/red]"
        else:
            status = f"Last updated: [bold]{self._last_updated}[/bold]"
        self.update(f"{status}  ·  Next poll: {self._next_poll}s")


class ClaudeStatusApp(App):
    TITLE = "Claude Status"
    CSS = """
    Screen {
        layout: vertical;
        background: $surface;
    }
    ComponentRow {
        height: 5;
        border: solid $panel-lighten-1;
        padding: 0 1;
        margin: 0;
    }
    IncidentBanner {
        height: auto;
        background: $warning 15%;
        padding: 0 1;
        margin: 0;
    }
    IncidentBanner.hidden {
        display: none;
    }
    StatusFooter {
        height: 1;
        dock: bottom;
        background: $panel;
        padding: 0 1;
    }
    """

    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self) -> None:
        super().__init__()
        self._history: list[PollRecord] = []
        self._prev_claude_code: str = "unknown"
        self._prev_claude_api: str = "unknown"

    def compose(self) -> ComposeResult:
        yield ComponentRow("Claude Code", "claude_code", id="row-claude-code")
        yield ComponentRow("Claude API (api.anthropic.com)", "claude_api", id="row-claude-api")
        yield IncidentBanner(id="incident-banner")
        yield StatusFooter(id="status-footer")

    def on_mount(self) -> None:
        self._history = load_history()
        if self._history:
            latest = self._history[-1]
            self._prev_claude_code = latest.claude_code
            self._prev_claude_api = latest.claude_api
            self._refresh_rows()
        self._do_poll()
        self.set_interval(POLL_INTERVAL, self._do_poll)

    def _refresh_rows(self) -> None:
        if not self._history:
            return
        latest = self._history[-1]
        self.query_one("#row-claude-code", ComponentRow).update_data(
            self._history, latest.claude_code
        )
        self.query_one("#row-claude-api", ComponentRow).update_data(
            self._history, latest.claude_api
        )

    def _do_poll(self) -> None:
        self._poll_worker()

    @work(thread=True)
    def _poll_worker(self) -> None:
        result = fetch_status()
        self.call_from_thread(self._handle_result, result)

    def _handle_result(self, result) -> None:
        footer = self.query_one("#status-footer", StatusFooter)

        if result.error or result.record is None:
            footer.mark_polled(error=result.error or "unknown error")
            return

        record = result.record
        append_record(record)
        self._history.append(record)

        check_and_notify("Claude Code", self._prev_claude_code, record.claude_code)
        check_and_notify("Claude API", self._prev_claude_api, record.claude_api)
        self._prev_claude_code = record.claude_code
        self._prev_claude_api = record.claude_api

        self._refresh_rows()
        self.query_one("#incident-banner", IncidentBanner).update_incidents(result.incidents)
        footer.mark_polled()
```

- [ ] **Step 4: Run the logic tests**

```bash
python3.12 -m pytest tests/test_app_logic.py -v
```

Expected: 9 tests pass.

- [ ] **Step 5: Run all tests so far**

```bash
python3.12 -m pytest -v
```

Expected: All tests pass (history + poller + notifier + app_logic).

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_app_logic.py
git commit -m "feat: app module — widgets, logic functions, ClaudeStatusApp"
```

---

## Task 6: Entry Point + Smoke Test

**Files:**
- Create: `claude_status.py`

- [ ] **Step 1: Write claude_status.py**

Create `claude_status.py`:

```python
#!/usr/bin/env python3.12
from app import ClaudeStatusApp

if __name__ == "__main__":
    ClaudeStatusApp().run()
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x ~/mjs/claude-status/claude_status.py
```

- [ ] **Step 3: Run a live smoke test**

```bash
cd ~/mjs/claude-status
python3.12 claude_status.py
```

Expected:
- TUI launches in terminal
- Two `ComponentRow` widgets visible: "Claude Code" and "Claude API (api.anthropic.com)"
- Status badges colored appropriately (green = operational, orange = degraded)
- Bar chart fills from the left as poll records accumulate
- Status footer shows "Last updated: HH:MM:SS · Next poll: 60s"
- If an active incident exists, a yellow `⚠` banner appears
- Press `q` to quit

- [ ] **Step 4: Verify history file was written**

```bash
cat ~/.local/share/claude-status/history.json
```

Expected: One or more lines of NDJSON, e.g.:
```json
{"ts": 1713196800, "claude_code": "degraded_performance", "claude_api": "operational"}
```

- [ ] **Step 5: Run again and verify history loads**

```bash
python3.12 claude_status.py
```

Expected: Bar chart starts with the previously saved records visible (not empty).

- [ ] **Step 6: Commit**

```bash
git add claude_status.py
git commit -m "feat: entry point — claude_status.py"
```

---

## Task 7: Final Polish + README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Run full test suite one final time**

```bash
cd ~/mjs/claude-status
python3.12 -m pytest -v
```

Expected: All tests pass, no warnings.

- [ ] **Step 2: Write README.md**

Create `README.md`:

```markdown
# claude-status

Terminal dashboard for monitoring Claude Code and Claude API health.

## Setup

```bash
pip3.12 install textual==8.2.3
```

## Run

```bash
python3.12 claude_status.py
```

Press `q` to quit.

## What it shows

- **Claude Code** and **Claude API** status (Operational / Degraded / Outage)
- Session-accumulated bar chart — one bar per 60s poll, persisted across restarts
- Active incident banner when the statuspage reports an open incident
- cmux notification on status change (when running inside cmux)

## Data

Poll history stored at `~/.local/share/claude-status/history.json` (NDJSON, one record per line).
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: README with setup and usage"
```

---

## Self-Review Checklist

- [x] **Spec coverage:** Layout (ComponentRow × 2, IncidentBanner, StatusFooter) ✓ · Session history (load on mount, append each poll) ✓ · Status colors ✓ · 60s poll interval ✓ · cmux notify on transition ✓ · Incident banner ✓ · Error handling (stale indicator, corrupt history) ✓ · Terminal-width-responsive bars ✓ · Minimum width fallback (fallback=(80,24)) ✓
- [x] **Placeholder scan:** No TBDs. All code complete.
- [x] **Type consistency:** `PollRecord` defined in Task 2, used consistently in Tasks 3–5. `Incident`/`FetchResult` defined in Task 3, used in Tasks 5. `detect_transition` returns `str | None` in Task 4, consumed in `check_and_notify` correctly. `mark_polled` defined and called consistently.
