# Claude Status TUI — Design Spec

**Date:** 2026-04-15  
**Status:** Approved

---

## Overview

A Textual-based TUI dashboard that polls the Claude statuspage API to monitor the health of Claude Code and the Claude API in real time. Displays a session-accumulated bar chart history, a current status callout, an active incident banner, and fires cmux notifications on status changes.

The history reflects the user's local session — not global 90-day uptime — making it contextually relevant to their actual dev experience.

---

## Architecture

### Single-file script

`~/dev/claude-status/claude_status.py`

Run directly: `python claude_status.py`

One dependency beyond stdlib: `textual`. No packaging, no virtualenv required beyond `pip install textual`.

### Data persistence

Poll results are appended to:

```
~/.local/share/claude-status/history.json
```

Format — one JSON object per line (newline-delimited JSON):

```json
{"ts": 1713196800, "claude_code": "degraded_performance", "claude_api": "operational"}
```

On startup, existing history is loaded and rendered. Each poll appends a new record. File is created automatically on first run.

### Polling

- **Interval:** 60 seconds
- **Components endpoint:** `https://status.claude.com/api/v2/components.json`
  - Claude Code component ID: `yyzkbfz2thpt`
  - Claude API component ID: `k8w3r06qmzrp`
- **Incidents endpoint:** `https://status.claude.com/api/v2/incidents/unresolved.json`
- Both fetched on each poll tick. Network errors are caught; previous status is retained with a visual "stale" indicator.

---

## Layout

```
┌─────────────────────────────────────────────────────────┐
│ Claude Code                      ● Degraded Performance │
│ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▒▒░░░░▒▒▓▓▓▓▓▓▓▓▓▓▓▓▓▒▒▒▒  │
│ Session start ──────────────── 97.2% uptime ─────── Now │
├─────────────────────────────────────────────────────────┤
│ Claude API (api.anthropic.com)           ● Operational  │
│ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  │
│ Session start ──────────────── 100% uptime ──────── Now │
├─────────────────────────────────────────────────────────┤
│ ⚠ Elevated errors on Claude.ai, API, Claude Code        │
│   Identified · 15 min ago                               │
├─────────────────────────────────────────────────────────┤
│ Last updated: 14:32:07  ·  Next poll: 47s               │
└─────────────────────────────────────────────────────────┘
```

- Two `ComponentRow` widgets stacked vertically, one per monitored service
- `IncidentBanner` widget below — hidden when no active incidents
- `StatusBar` at the bottom with last-updated timestamp and countdown to next poll
- Terminal-width-responsive: bar chart fills available width, truncates oldest bars first when narrow

---

## Components

### `ComponentRow`

Renders one service. Props: `name`, `history: list[PollRecord]`, `current_status`.

- **Header line:** service name left, colored status badge right
- **Bar chart:** one bar character per poll record, colored by status, fills terminal width (most recent = rightmost, oldest dropped when space runs out)
- **Footer line:** "Session start" left, uptime % center, "Now" right

Bar character mapping:
- `operational` → `█` green
- `degraded_performance` → `█` orange  
- `partial_outage` → `█` red
- `major_outage` → `█` bold red
- `unknown` / fetch error → `░` dim (stale indicator)

### `IncidentBanner`

Shown only when `incidents/unresolved.json` returns one or more incidents. Displays each active incident as its own line: name, status label, and age ("15 min ago", "2 hr ago"). Hidden when no active incidents. In practice there is rarely more than one active incident; if there are multiple, all are shown stacked.

### `StatusBar`

Single footer line: last poll timestamp + countdown to next poll (counts down from 60).

---

## Notifications

On each poll, compare new status to previous status per component:

- **Degraded/outage** (was operational, now not): fire `cmux notify --title "Claude Code degraded" --body "<status label>"`
- **Recovery** (was not operational, now operational): fire `cmux notify --title "Claude Code recovered" --body "Back to operational"`

cmux detection: check `CMUX_WORKSPACE_ID` env var. If not set, skip notify silently — the TUI still updates normally.

Notify once per transition, not on every poll.

---

## Error Handling

- **Network error on poll:** retain last known status, mark bars as stale (`░`), show "fetch failed" in status bar. Retry next interval.
- **History file unreadable/corrupt:** start fresh, log warning to status bar, do not crash.
- **Terminal too narrow to render bars:** show at least the status badge and name; suppress bar chart below a minimum width (40 chars).

---

## File Structure

```
~/dev/claude-status/
├── claude_status.py         # single-file TUI app
├── requirements.txt         # textual pinned to latest stable at implementation time
└── docs/
    └── superpowers/
        └── specs/
            └── 2026-04-15-claude-status-tui-design.md
```

Data directory (outside repo):
```
~/.local/share/claude-status/
└── history.json             # newline-delimited JSON poll records
```

---

## Out of Scope

- More than two components (can be added later by changing a config list)
- Interactive keyboard navigation / scrolling history
- Alerting via channels other than cmux (email, Slack, etc.)
- Packaging / distribution
