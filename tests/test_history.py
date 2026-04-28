import json
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


def test_load_history_skips_corrupt_lines_keeps_valid(tmp_path):
    test_file = tmp_path / "history.json"
    test_file.write_text(
        '{"ts": 1, "claude_code": "operational", "claude_api": "operational"}\n'
        'not valid json\n'
        '{"ts": 2, "claude_code": "operational", "claude_api": "operational"}\n'
    )
    with patch("history.HISTORY_FILE", test_file):
        loaded = load_history()
    assert len(loaded) == 2
    assert loaded[0].ts == 1
    assert loaded[1].ts == 2
