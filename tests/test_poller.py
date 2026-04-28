import json
import urllib.error
from unittest.mock import MagicMock
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
    return lambda url, timeout, **kwargs: next(it)


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


def test_fetch_status_preserves_record_when_incidents_fail(monkeypatch):
    call_count = 0
    def mock_urlopen(url, timeout, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_response(MOCK_COMPONENTS)
        raise urllib.error.URLError("incidents endpoint unreachable")
    monkeypatch.setattr("poller.urllib.request.urlopen", mock_urlopen)
    result = fetch_status()
    assert result.record is not None
    assert result.record.claude_code == "operational"
    assert result.error is not None
    assert result.incidents == []
