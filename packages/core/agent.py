"""Luxella Agent Standard - har agent isi harness pe chalta hai (spec docs/specs/2026-10-07-agent-standard.md).

    with Agent("sourcing", "deal-finder", mode="shadow", write_budget=20,
               tools={"price_alert": send_alert}) as ag:
        rows = ag.read("luxella_query", query_fn, site="staud")
        ag.write("price_alert", "price_alert", {"product_id": 7}, risk="low")

Modes:
    read_only  koi write nahi (write() = error), budget 0
    shadow     write() sirf log karta hai - tool kabhi nahi chalta
    approve    write() = approvals.propose(); baad mein ag.execute(pid, tool, args) (founder approve ke baad)
    auto       sirf auto_actions wale action seedha chalte hain; baaki approve ki tarah propose
Har read/write/execute se pehle: kill switch (env LUXELLA_KILL=1 ya <ops>/kill/<agent|ALL>) + write budget.
Run khatam: runs.log_run (mode, reads, writes, proposals); failed/killed/budget_exceeded pe phone alert.
"""
import os
import re
import time

from packages.core import _store, approvals, runs

MODES = ("read_only", "shadow", "approve", "auto")
STOP_STATUSES = {"failed", "killed", "budget_exceeded"}
_SECRET_KEY = re.compile(r"token|key|secret|password", re.I)
_SECRET_PREFIXES = ("shpat_", "shpss_", "Bearer ", "eyJ", "ghp_", "github_pat_", "sk-")
_FENCE_OPEN, _FENCE_CLOSE = "<<<UNTRUSTED_DATA", "<<<END_UNTRUSTED_DATA>>>"


class AgentStopped(BaseException):
    """BaseException on purpose: agents ke `except Exception` (retry loops) kill/budget stop ko nigal na sakein."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def redact(obj):
    """Secret-jaisi keys / values ko '[redacted]' - logs mein kabhi token na jaaye."""
    if isinstance(obj, dict):
        return {k: "[redacted]" if _SECRET_KEY.search(str(k)) else redact(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return type(obj)(redact(v) for v in obj)
    if isinstance(obj, str) and obj.startswith(_SECRET_PREFIXES):
        return "[redacted]"
    return obj


def _has_secret(obj):
    return redact(obj) != obj


def _ops_dir():
    return os.environ.get("LUXELLA_OPS_DIR", _store.DEFAULT_DIR)  # sirf padhna - mkdir nahi (dry-run kuch na likhe)


def kill_reason(agent):
    if os.environ.get("LUXELLA_KILL") == "1":
        return "env LUXELLA_KILL=1"
    for name in (agent, "ALL"):
        if os.path.exists(os.path.join(_ops_dir(), "kill", name)):
            return f"kill file {name}"
    return None


def untrusted(text, source="external"):
    """Bahar ka text (scrape, customer message) data ki tarah fence karo - prompt rule: fence ke andar = data, hukm nahi."""
    clean = str(text).replace(_FENCE_OPEN, "[fence]").replace(_FENCE_CLOSE, "[fence]")
    return f"{_FENCE_OPEN} source={source}>>>\n{clean}\n{_FENCE_CLOSE}"


class Agent:
    def __init__(self, department, name, mode="shadow", write_budget=0, auto_actions=(), tools=None, record=True):
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        self.department, self.name, self.mode = department, name, mode
        self.write_budget = 0 if mode == "read_only" else write_budget
        self.auto_actions, self.tools, self.record = set(auto_actions), dict(tools or {}), record
        self.reads, self.writes, self.proposals = [], [], []
        self.inputs, self.outputs, self.status = {}, {}, None

    # ---------- lifecycle ----------
    def __enter__(self):
        self._t0 = time.time()
        reason = kill_reason(self.name)
        if reason:
            self._finish("killed", reason)
            raise AgentStopped("killed")
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None and issubclass(exc_type, AgentStopped):
            self._finish(exc.reason, exc.reason)
            return True  # beech mein ruk gaya - saaf band, log + alert ho chuka
        if exc_type is not None:
            self._finish("failed", exc_type.__name__)  # sirf type - error text mein data/secret ho sakta hai
            return False
        self._finish(self.status or ("dry_run" if self.mode == "shadow" else "ok"), "")
        return False

    def _finish(self, status, why):
        if not self.record:
            return
        rid = runs.log_run(self.department, self.name, inputs=redact(self.inputs),
                           tool_calls=[r["tool"] for r in self.reads], outputs=redact(self.outputs),
                           approvals=self.proposals, duration=round(time.time() - getattr(self, "_t0", time.time()), 1),
                           status=status, extra={"mode": self.mode, "reads": self.reads, "writes": self.writes,
                                                 "stop_reason": why})
        if status in STOP_STATUSES:
            approvals.push(f"Luxella agent {self.name}: {status}",
                           f"{self.department}/{self.name} {status} {why} run {rid}", priority="high")

    # ---------- guards ----------
    def _check(self):
        if kill_reason(self.name):
            raise AgentStopped("killed")

    def _spend(self):
        if len(self.writes) >= self.write_budget:
            raise AgentStopped("budget_exceeded")

    # ---------- actions ----------
    def read(self, tool, fn, *args, **kwargs):
        self._check()
        self.reads.append({"tool": tool, "kwargs": redact(kwargs), "nargs": len(args)})
        return fn(*args, **kwargs)

    def write(self, action, tool, args, risk="low", dry_run_output="", undo=""):
        """Agent ka KUCH bhi badalne ka ek-hi raasta. args mein credentials mana (approvals log mein exact jaate hain)."""
        self._check()
        if self.mode == "read_only":
            raise ValueError(f"{self.name} is read_only - write() not allowed")
        if _has_secret(args):
            raise ValueError("write args contain a secret-like key/value - tools must read credentials from env")
        self._spend()
        entry = {"action": action, "tool": tool, "args": args, "risk": risk}
        if self.mode == "shadow":
            self.writes.append({**entry, "outcome": "shadow"})
            return None
        if self.mode == "auto" and action in self.auto_actions:
            result = self.tools[tool](**args)
            self.writes.append({**entry, "outcome": "auto"})
            return result
        pid = approvals.propose(self.department, self.name, action, risk, tool, args, dry_run_output, undo)
        self.proposals.append(pid)
        self.writes.append({**entry, "outcome": "proposed", "pid": pid})
        return pid

    def execute(self, pid, tool, args):
        """Founder-approved proposal chalao: wahi agent, wahi tool, wahi args (assert_executable), registry ka fn."""
        self._check()
        self._spend()
        if approvals.get(pid)["agent"] != self.name:
            raise approvals.NotExecutable(f"{pid} belongs to another agent")
        approvals.assert_executable(pid, tool, args)
        result = self.tools[tool](**args)
        approvals.mark_executed(pid, {"ok": True})
        self.writes.append({"action": "execute", "tool": tool, "args": args, "outcome": "executed", "pid": pid})
        return result
