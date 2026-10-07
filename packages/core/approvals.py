"""Approval queue (approval-queue skill). An agent PROPOSES a risky action; the founder decides in chat;
the agent executes ONLY an approved proposal whose tool + args match exactly, via the tool's confirm=True path.

    from packages.core import approvals as aq
    pid = aq.propose("catalog", "curator", action="Set 5 drift products to stock 0", risk="med",
                     tool="inventorySetQuantities", args={...}, dry_run_output="...", undo="backup ...")
    aq.list_pending()
    aq.decide(pid, "approve", decided_by="founder")       # never the proposing agent
    aq.assert_executable(pid, tool, args)                 # raises unless approved, unexpired, exact match
    ... run the tool with confirm=True ...
    aq.mark_executed(pid, result={...})

Storage: <ops dir>/approvals.jsonl (append-only events, latest per id wins). Pending > 48h = expired.
New proposals ping ntfy (topic from LUXELLA_NTFY_TOPIC or the topic file; LUXELLA_NTFY=0 turns it off).
The push holds only the action line and id - never customer data or prices.

CLI:
    .venv/bin/python -m packages.core.approvals list
    .venv/bin/python -m packages.core.approvals selftest      # tempdir, no network
    .venv/bin/python -m packages.core.approvals notify-test   # sends ONE real push
"""
import json
import os
import sys
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

from packages.core import _store

FILE = "approvals.jsonl"
DECIDERS = {"founder"}  # sirf founder approve/reject kar sakta hai
EXPIRY = timedelta(hours=48)
RISKS = {"low", "med", "high"}
TOPIC_FILE = "/root/.config/agent-keys/uptime-kuma-ntfy-topic"


class NotExecutable(Exception):
    pass


def _now(now=None):
    return now or datetime.now(timezone.utc)


def _canon(args):
    return json.dumps(args, sort_keys=True, separators=(",", ":"), default=str)


def _events():
    return _store.read_all(_store.path_for(FILE))


def _state(now=None):
    """{id: record} - creation record merged with later status events; pending > 48h -> expired."""
    recs = {}
    for e in _events():
        if e.get("event") == "proposed":
            recs[e["id"]] = dict(e)
        elif e["id"] in recs:
            recs[e["id"]].update({k: v for k, v in e.items() if k not in ("event", "id")})
    for r in recs.values():
        # pending: created_at se 48h; approved par execute nahi hua: decided_at se 48h (purana batch mat chalao)
        since = r.get("decided_at") if r["status"] == "approved" else r["created_at"]
        if r["status"] in ("pending", "approved") and _now(now) - datetime.fromisoformat(since) > EXPIRY:
            r["status"] = "expired"
    return recs


def propose(department, agent, action, risk, tool, args, dry_run_output="", undo="", notify=True):
    if risk not in RISKS:
        raise ValueError(f"risk must be one of {sorted(RISKS)}")
    pid = f"a-{uuid.uuid4().hex[:10]}"
    _store.append(_store.path_for(FILE), {
        "event": "proposed", "id": pid, "created_at": _now().isoformat(), "department": department,
        "agent": agent, "action": action, "risk": risk, "tool": tool, "args": args,
        "dry_run_output": dry_run_output, "undo": undo, "status": "pending"})
    if notify:
        _notify(pid, action, risk)
    return pid


def get(pid, now=None):
    rec = _state(now).get(pid)
    if not rec:
        raise KeyError(f"no proposal {pid}")
    return rec


def list_pending(now=None):
    return [r for r in _state(now).values() if r["status"] == "pending"]


def decide(pid, decision, decided_by, note="", now=None):
    rec = get(pid, now)
    if decision not in ("approve", "reject"):
        raise ValueError("decision must be approve or reject")
    if rec["status"] != "pending":
        raise NotExecutable(f"{pid} is {rec['status']}, cannot {decision}")
    who = (decided_by or "").strip().lower()
    if who not in DECIDERS or who == str(rec["agent"]).strip().lower():
        raise PermissionError("only the founder decides - decided_by must be 'founder', never an agent")
    status = "approved" if decision == "approve" else "rejected"
    _store.append(_store.path_for(FILE), {"event": "decided", "id": pid, "status": status,
                                          "decided_by": decided_by, "decided_at": _now(now).isoformat(),
                                          "note": note})
    return status


def assert_executable(pid, tool, args, now=None):
    rec = get(pid, now)
    if rec["status"] != "approved":
        raise NotExecutable(f"{pid} is {rec['status']} - only approved proposals run")
    if rec["tool"] != tool or _canon(rec["args"]) != _canon(args):
        raise NotExecutable(f"{pid}: tool/args differ from what was approved - re-propose")
    return rec


def mark_executed(pid, result, now=None):
    rec = get(pid, now)
    if rec["status"] != "approved":
        raise NotExecutable(f"{pid} is {rec['status']}")
    _store.append(_store.path_for(FILE), {"event": "executed", "id": pid, "status": "executed",
                                          "executed_at": _now(now).isoformat(), "result": result})


def _topic():
    t = os.environ.get("LUXELLA_NTFY_TOPIC", "").strip()
    if not t and os.path.exists(TOPIC_FILE):
        t = open(TOPIC_FILE).read().strip()
    return t


def push(title, body, priority="default", tags="", *, card=None, buttons=None):
    """Founder ko notification: pehle Telegram (card + buttons, agar configured), warna/aur ntfy (sirf body).
    High priority (agent failed/killed/budget) dono pe jaata hai. Kabhi raise nahi karta - fail = False."""
    from packages.core import telegram
    tg_ok = telegram.send(card or f"{title}\n{body}", buttons)
    if tg_ok and priority != "high":
        return True
    return _ntfy(title, body, priority, tags) or tg_ok


def _ntfy(title, body, priority, tags):
    if os.environ.get("LUXELLA_NTFY", "1") == "0":
        return False
    topic = _topic()
    if not topic:
        print("[ntfy] topic not set - no push", file=sys.stderr)
        return False
    server = os.environ.get("LUXELLA_NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    headers = {"Title": title, "Priority": priority}
    if tags:
        headers["Tags"] = tags
    req = urllib.request.Request(f"{server}/{topic}", data=body.encode(), method="POST", headers=headers)
    try:
        urllib.request.urlopen(req, timeout=10).read()
        return True
    except Exception as e:  # never block the caller on a failed push
        print(f"[ntfy] push failed: {type(e).__name__}", file=sys.stderr)
        return False


def proposal_card(rec):
    from packages.core.agent import redact  # lazy: agent imports approvals
    args = ", ".join(f"{k}={str(v)[:80]}" for k, v in redact(rec.get("args") or {}).items())
    return (f"Approval needed ({rec.get('risk')})\n{rec.get('agent')}: {str(redact([rec.get('action')])[0])[:300]}\n"
            f"tool: {rec.get('tool')}\nargs: {args or '-'}\nid: {rec['id']}")


def approval_buttons(pid):
    return [[("✅ Approve", f"a:{pid}"), ("❌ Reject", f"r:{pid}")]]


def _notify(pid, action, risk):
    rec = _state().get(pid)  # notify-test fake id ka koi record nahi - tab sirf plain text, bina buttons
    return push(f"Luxella approval needed ({risk})", f"{action[:120]} [{pid}]", tags="inbox_tray",
                card=proposal_card(rec) if rec else None, buttons=approval_buttons(pid) if rec else None)


def _selftest():
    import tempfile

    def no_network(*a, **k):
        raise AssertionError("selftest must not touch the network")
    urllib.request.urlopen = no_network
    os.environ["LUXELLA_OPS_DIR"] = tempfile.mkdtemp()
    os.environ["LUXELLA_NTFY"] = "0"
    os.environ["LUXELLA_TELEGRAM"] = "0"

    args = {"items": ["i1", "i2"], "qty": 0}
    pid = propose("catalog", "curator", "Set 2 sizes to 0", "med", "inventorySetQuantities", args)
    assert [r["id"] for r in list_pending()] == [pid]
    try:
        decide(pid, "approve", decided_by="curator")
        raise AssertionError("self-approval accepted")
    except PermissionError:
        pass
    for who in ("Curator", " curator ", "scout"):
        try:
            decide(pid, "approve", decided_by=who)
            raise AssertionError(f"non-founder {who!r} approved")
        except PermissionError:
            pass
    try:
        assert_executable(pid, "inventorySetQuantities", args)
        raise AssertionError("pending executed")
    except NotExecutable:
        pass
    assert decide(pid, "approve", decided_by="founder") == "approved"
    assert_executable(pid, "inventorySetQuantities", {"qty": 0, "items": ["i1", "i2"]})  # key order irrelevant
    for bad_tool, bad_args in (("inventorySetQuantities", {**args, "qty": 10}), ("productDelete", args)):
        try:
            assert_executable(pid, bad_tool, bad_args)
            raise AssertionError("mismatch executed")
        except NotExecutable:
            pass
    mark_executed(pid, {"ok": True})
    assert get(pid)["status"] == "executed" and list_pending() == []

    old = propose("catalog", "curator", "old", "low", "t", {}, notify=False)
    assert get(old, now=_now() + timedelta(hours=49))["status"] == "expired"
    try:
        decide(old, "approve", "founder", now=_now() + timedelta(hours=49))
        raise AssertionError("expired approved")
    except NotExecutable:
        pass
    stale = propose("catalog", "curator", "stale batch", "med", "t", {"n": 5}, notify=False)
    decide(stale, "approve", "Founder")
    assert_executable(stale, "t", {"n": 5})
    try:
        assert_executable(stale, "t", {"n": 5}, now=_now() + timedelta(hours=49))
        raise AssertionError("approved-but-unexecuted batch ran after 48h")
    except NotExecutable:
        pass
    # kharab line (valid JSON, record nahi) se queue nahi girni chahiye
    with open(_store.path_for(FILE), "a") as f:
        f.write("[1]\n\"x\"\n")
    list_pending()
    rej = propose("sales", "concierge", "reply", "high", "send_dm", {"to": "x"}, notify=False)
    assert decide(rej, "reject", "founder") == "rejected"
    print("approvals selftest ok")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "selftest":
        _selftest()
    elif cmd == "notify-test":
        print("sent" if _notify("a-test", "Test push from Luxella approval queue", "low") else "not sent")
    elif cmd == "list":
        for r in list_pending():
            print(f"{r['id']}  [{r['risk']}] {r['department']}/{r['agent']}: {r['action']}  ({r['created_at'][:16]})")
    else:
        print(__doc__)
