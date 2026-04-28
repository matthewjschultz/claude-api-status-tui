import json
import ssl
import time
import urllib.request
from dataclasses import dataclass, field

import certifi

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
    ctx = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(url, timeout=10, context=ctx) as resp:
        data = json.loads(resp.read())
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object from {url}, got {type(data).__name__}")
    return data


def fetch_status() -> FetchResult:
    try:
        components_data = _fetch_json(COMPONENTS_URL)
        by_id = {c["id"]: c["status"] for c in components_data["components"]}
        record = PollRecord(
            ts=int(time.time()),
            claude_code=by_id.get(CLAUDE_CODE_ID, "unknown"),
            claude_api=by_id.get(CLAUDE_API_ID, "unknown"),
        )
    except Exception as exc:
        return FetchResult(record=None, error=str(exc))

    try:
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
        return FetchResult(record=record, incidents=[], error=str(exc))
