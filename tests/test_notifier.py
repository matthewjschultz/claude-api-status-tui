import os
from unittest.mock import patch
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
    assert "Degraded Performance" in args


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


def test_detect_unknown_old_returns_none():
    assert detect_transition("unknown", "operational") is None


def test_detect_unknown_new_returns_none():
    assert detect_transition("operational", "unknown") is None


def test_notify_cmux_binary_missing_does_not_raise():
    with patch.dict(os.environ, {"CMUX_WORKSPACE_ID": "workspace:1"}):
        with patch("notifier.subprocess.run", side_effect=FileNotFoundError):
            # should not raise
            notify_cmux("title", "body")
