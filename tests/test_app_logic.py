from history import PollRecord
from app import render_bar, uptime_percent, _format_age


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
    assert "▉" in bar


def test_render_bar_degraded_uses_orange():
    bar = render_bar([_deg(1)], "claude_code", width=10)
    assert "orange3" in bar


def test_render_bar_truncates_to_width():
    history = [_op(i) for i in range(20)]
    # 1 char per bar; width=10 fits exactly 10 bars
    bar = render_bar(history, "claude_code", width=10)
    assert bar.count("▉") == 10


def test_render_bar_no_separator_character():
    history = [_op(i) for i in range(3)]
    bar = render_bar(history, "claude_code", width=20)
    # No explicit separator — relies on natural cell boundary between █ chars
    assert "│" not in bar
    assert " " not in bar


def test_render_bar_shows_all_when_fewer_than_width():
    history = [_op(i) for i in range(3)]
    bar = render_bar(history, "claude_code", width=10)
    assert bar.count("▉") == 3


def test_render_bar_unknown_uses_dim_block():
    record = PollRecord(ts=1, claude_code="unknown", claude_api="operational")
    bar = render_bar([record], "claude_code", width=10)
    assert "░" in bar
    assert "dim" in bar


def test_format_age_seconds():
    from datetime import datetime, timezone, timedelta
    ts = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
    assert _format_age(ts) == "30s ago"


def test_format_age_minutes():
    from datetime import datetime, timezone, timedelta
    ts = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
    assert _format_age(ts) == "15 min ago"


def test_format_age_hours():
    from datetime import datetime, timezone, timedelta
    ts = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    assert _format_age(ts) == "3 hr ago"


def test_format_age_malformed_returns_unknown():
    assert _format_age("not-a-date") == "unknown age"
