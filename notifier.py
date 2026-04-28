import os
import subprocess


_DEGRADED_STATUSES = frozenset({
    "degraded_performance",
    "partial_outage",
    "major_outage",
})


def detect_transition(old: str, new: str) -> str | None:
    """Returns 'degraded', 'recovered', or None.

    'unknown' is treated as neutral — it represents a polling failure,
    not an actual service status change, so it never triggers notifications.
    """
    if old == "unknown" or new == "unknown":
        return None
    was_ok = old == "operational"
    is_ok = new == "operational"
    if was_ok and new in _DEGRADED_STATUSES:
        return "degraded"
    if old in _DEGRADED_STATUSES and is_ok:
        return "recovered"
    return None


def notify_cmux(title: str, body: str) -> None:
    if not os.environ.get("CMUX_WORKSPACE_ID"):
        return
    try:
        subprocess.run(
            ["cmux", "notify", "--title", title, "--body", body],
            capture_output=True,
        )
    except (FileNotFoundError, OSError):
        pass  # cmux not available; notification is best-effort


def check_and_notify(component_name: str, old_status: str, new_status: str) -> None:
    transition = detect_transition(old_status, new_status)
    if transition == "degraded":
        label = new_status.replace("_", " ").title()
        notify_cmux(f"{component_name} degraded", label)
    elif transition == "recovered":
        notify_cmux(f"{component_name} recovered", "Back to operational")
