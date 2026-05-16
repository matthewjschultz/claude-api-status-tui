# CLAUDE.md — claude-api-status-tui

TUI dashboard that monitors Claude Code and Claude API health from the official statuspage.

## Run

```bash
uv run claude_status.py
# or directly (shebang handles uv invocation):
./claude_status.py
```

No install step — `uv` fetches dependencies (`textual==8.2.3`, `certifi`) on first run.

Press `q` to quit.

## Tests

```bash
uv run --with pytest --with "textual==8.2.3" --with certifi pytest tests/ -q
```

## Project Structure

| File | Purpose |
|------|---------|
| `claude_status.py` | Entry point. PEP 723 inline metadata for `uv run`. |
| `app.py` | Textual `ClaudeStatusApp`. Layout, polling loop, UI refresh. |
| `poller.py` | Fetches `/api/v2/components.json` + `/api/v2/incidents/unresolved.json`. Returns `FetchResult`. |
| `history.py` | NDJSON read/write at `~/.local/share/claude-status/history.json`. `PollRecord` dataclass. |
| `notifier.py` | Detects operational ↔ degraded transitions. Fires `cmux notify` if `CMUX_WORKSPACE_ID` is set. |
| `tests/` | pytest unit tests for poller, history, app logic, and notifier. |

## Architecture

- **Polling**: `_poll_worker` runs in a background thread (`@work(thread=True, exit_on_error=False)`) every 60 seconds and on mount.
- **Thread safety**: Results are dispatched back to the main thread via `self.call_from_thread(self._handle_result, result)`.
- **Persistence**: Every successful poll appends a `PollRecord` to NDJSON history. History is loaded on startup and seeded into the in-memory list.
- **Bar chart**: `ComponentRow._redraw()` renders one `█` per historical record (last N to fit width). Colors encode status.
- **SSL**: Uses `certifi` CA bundle via `ssl.create_default_context(cafile=certifi.where())` — required on macOS.

## Statuspage Component IDs

```python
CLAUDE_CODE_ID = "yyzkbfz2thpt"   # "Claude Code" on status.claude.com
CLAUDE_API_ID  = "k8w3r06qmzrp"   # "Claude API (api.anthropic.com)"
```

These are stable IDs from the statuspage API. If components ever stop returning data, verify against:
```
curl https://status.claude.com/api/v2/components.json | python -m json.tool | grep -A2 '"name"'
```

## Known Gotchas

### `shutil` vs `os` for terminal size
`shutil.get_terminal_size(fallback=(80, 24))` accepts a `fallback` kwarg. `os.get_terminal_size()` does NOT — it raises `TypeError: posix.get_terminal_size() takes no keyword arguments`.

The fallback path in `ComponentRow._redraw()` is triggered when `self.size.width == 0`, which happens during `on_mount` before Textual has laid out the widget. This only occurs when history exists on startup (causing `_refresh_rows()` to run immediately on mount). **Always use `shutil.get_terminal_size`** for the fallback.

### History file format
`~/.local/share/claude-status/history.json` is NDJSON (one JSON object per line). Corrupt lines are silently skipped — the file is not all-or-nothing.

### Partial fetch failure handling
`fetch_status()` uses two separate `try` blocks:
1. Fetch components → build `PollRecord`. If this fails, return `FetchResult(record=None, error=...)`.
2. Fetch incidents. If this fails, return `FetchResult(record=record, incidents=[], error=...)`.

This means a valid `record` is preserved even when the incidents endpoint is unreachable. `_handle_result` in `app.py` checks `if result.record is None` (not `if result.error`) — don't change this.

### cmux notifications
`notifier.py` only calls `cmux notify` when `CMUX_WORKSPACE_ID` is set in the environment. Transitions from/to `"unknown"` are suppressed (polling failures don't trigger alerts).

### Textual widget sizing
`ComponentRow` has `height: 5` in CSS (label line + bar line + footer line + 2 border lines). If you add content rows, bump this.

## Status Values

From the statuspage API:
- `operational`
- `degraded_performance`
- `partial_outage`
- `major_outage`
- `unknown` (synthesized locally when component is missing from API response)
