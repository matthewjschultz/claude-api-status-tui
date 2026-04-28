# claude-status

Terminal dashboard for monitoring Claude Code and Claude API health.

## Run

```bash
uv run claude_status.py
```

Or directly (shebang handles it):

```bash
./claude_status.py
```

No install step needed — `uv` fetches dependencies on first run.

Press `q` to quit.

## What it shows

- **Claude Code** and **Claude API** status (Operational / Degraded / Outage)
- Session-accumulated bar chart — one bar per 60s poll, persisted across restarts
- Active incident banner when the statuspage reports an open incident
- cmux notification on status change (when running inside cmux)

## Data

Poll history stored at `~/.local/share/claude-status/history.json` (NDJSON, one record per line).
