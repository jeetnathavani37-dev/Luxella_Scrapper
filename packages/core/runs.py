"""Agent run log (kpi-report skill). One JSONL line per agent run in <ops dir>/agent_runs.jsonl.

    from packages.core.runs import log_run
    log_run("catalog", "curator", inputs={...}, tool_calls=[...], outputs={...}, approvals=["a-..."],
            duration=12.3, status="ok")

Selftest: .venv/bin/python -m packages.core.runs selftest
"""
import sys
import uuid
from datetime import datetime, timezone

from packages.core import _store

FILE = "agent_runs.jsonl"
STATUSES = {"ok", "partial", "failed", "dry_run"}


def log_run(department, agent, inputs=None, tool_calls=None, outputs=None, approvals=None,
            duration=None, status="ok"):
    if status not in STATUSES:
        raise ValueError(f"status must be one of {sorted(STATUSES)}")
    rec = {"id": f"r-{uuid.uuid4().hex[:12]}", "at": datetime.now(timezone.utc).isoformat(),
           "department": department, "agent": agent, "inputs": inputs or {}, "tool_calls": tool_calls or [],
           "outputs": outputs or {}, "approvals": approvals or [], "duration_s": duration, "status": status}
    _store.append(_store.path_for(FILE), rec)
    return rec["id"]


def recent(n=20, department=None):
    rows = _store.read_all(_store.path_for(FILE))
    if department:
        rows = [r for r in rows if r.get("department") == department]
    return rows[-n:]


def _selftest():
    import os
    import tempfile
    os.environ["LUXELLA_OPS_DIR"] = tempfile.mkdtemp()
    rid = log_run("catalog", "curator", inputs={"limit": 5}, tool_calls=["luxella_check_availability"],
                  outputs={"drift": 3}, duration=1.5, status="dry_run")
    rows = recent()
    assert len(rows) == 1 and rows[0]["id"] == rid and rows[0]["outputs"]["drift"] == 3
    assert oct(os.stat(_store.path_for(FILE)).st_mode & 0o777) == "0o600"
    try:
        log_run("catalog", "curator", status="weird")
        raise AssertionError("bad status accepted")
    except ValueError:
        pass
    print("runs selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        _selftest()
    else:
        print(__doc__)
