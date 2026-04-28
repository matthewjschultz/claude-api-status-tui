import os
import shutil
from datetime import datetime, timezone

from textual.app import App, ComposeResult
from textual.widgets import Static
from textual import work

from history import PollRecord, load_history, append_record
from poller import fetch_status, FetchResult, Incident
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
    "operational": ("▉", "green"),
    "degraded_performance": ("▉", "orange3"),
    "partial_outage": ("▉", "red"),
    "major_outage": ("▉", "bold red"),
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
        delta = max(0, int((datetime.now(timezone.utc) - ts).total_seconds()))
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
        width = self.size.width - 4 if self.size.width > 4 else shutil.get_terminal_size(fallback=(80, 24)).columns - 4
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
        padding: 0;
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
        self._poll_worker()
        self.set_interval(POLL_INTERVAL, self._poll_worker)

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

    @work(thread=True, exit_on_error=False)
    def _poll_worker(self) -> None:
        result = fetch_status()
        self.call_from_thread(self._handle_result, result)

    def _handle_result(self, result: FetchResult) -> None:
        footer = self.query_one("#status-footer", StatusFooter)

        if result.record is None:
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
        footer.mark_polled(error=result.error)
