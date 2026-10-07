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
import json
import os
import re
import sys
import time

from packages.core import _store, approvals, runs

MODES = ("read_only", "shadow", "approve", "auto")
STOP_STATUSES = {"failed", "killed", "budget_exceeded"}
_SECRET_KEY = re.compile(r"token|api[_-]?key|secret|password|authorization|credential", re.I)  # plain "key" (metafield) ok
_SECRET_PREFIXES = ("shpat_", "shpss_", "Bearer ", "eyJ", "ghp_", "github_pat_", "sk-", "sb_secret_", "fc-", "AIza")
_SECRET_INSIDE = re.compile(r"Bearer \S|[?&](token|key|secret|access_token)=", re.I)
_FENCE_OPEN, _FENCE_CLOSE = "<<<UNTRUSTED_DATA", "<<<END_UNTRUSTED_DATA>>>"
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REGISTRY = os.path.join(REPO, "agents.json")
MAX_BUDGET, MIN_CASES, MIN_TAGGED = 200, 20, 3
_NAME = re.compile(r"[a-z0-9-]+|ALL")  # fullmatch (newline wala naam nahi)


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
    if isinstance(obj, str) and (obj.startswith(_SECRET_PREFIXES) or _SECRET_INSIDE.search(obj)):
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


def killed_agents():
    kdir = os.path.join(_ops_dir(), "kill")
    return sorted(os.listdir(kdir)) if os.path.isdir(kdir) else []


def untrusted(text, source="external"):
    """Bahar ka text (scrape, customer message) data ki tarah fence karo - prompt rule: fence ke andar = data, hukm nahi."""
    clean = str(text).replace(_FENCE_OPEN, "[fence]").replace(_FENCE_CLOSE, "[fence]")
    return f"{_FENCE_OPEN} source={source}>>>\n{clean}\n{_FENCE_CLOSE}"


# ---------- registry (agents.json): mode sirf PR + review se badalta hai ----------

def load_registry(path=REGISTRY):
    with open(path) as f:
        return {e["name"]: e for e in json.load(f)["agents"]}


def check_registry(entries, repo=REPO):
    """CI gate: har registered agent ke liye niyam. Khaali list = sab theek."""
    errors = []
    for e in entries.values():
        n, mode, budget = e["name"], e.get("mode"), e.get("write_budget", 0)
        if mode not in MODES:
            errors.append(f"{n}: unknown mode {mode!r}")
        if mode == "read_only" and budget != 0:
            errors.append(f"{n}: read_only agents must have write_budget 0")
        if budget > MAX_BUDGET:
            errors.append(f"{n}: write_budget {budget} > {MAX_BUDGET}")
        if mode == "auto" and not e.get("auto_actions"):
            errors.append(f"{n}: auto mode needs a non-empty auto_actions list")
        entry = os.path.join(repo, e.get("entry", ""))
        if not os.path.isfile(entry) or "Agent(" not in open(entry).read():
            errors.append(f"{n}: entry {e.get('entry')!r} must exist and run on the Agent harness")
        if e.get("evals") == "unit-tests":
            if mode != "read_only":
                errors.append(f"{n}: the unit-tests eval exemption is only for read_only agents")
            continue
        path = os.path.join(repo, e.get("evals") or "-")
        cases = [json.loads(x) for x in open(path) if x.strip()] if os.path.isfile(path) else []
        tags = [t for c in cases for t in c.get("tags", [])]
        if len(cases) < MIN_CASES:
            errors.append(f"{n}: {len(cases)} eval cases, needs >= {MIN_CASES}")
        for tag in ("injection", "edge"):
            if tags.count(tag) < MIN_TAGGED:
                errors.append(f"{n}: needs >= {MIN_TAGGED} eval cases tagged {tag!r}")
    return errors


class Agent:
    def __init__(self, department, name, mode="shadow", write_budget=0, auto_actions=(), tools=None, record=True,
                 registry=None):
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        if not _NAME.fullmatch(name) or name == "ALL":
            raise ValueError(f"bad agent name {name!r}")
        if mode in ("approve", "auto"):  # code khud ko promote na kar sake: registry (PR) se match hona chahiye
            reg = (registry if registry is not None else load_registry()).get(name)
            if (not reg or reg.get("mode") != mode or write_budget > reg.get("write_budget", 0)
                    or not set(auto_actions) <= set(reg.get("auto_actions", []))):
                raise ValueError(f"{name}: {mode} mode needs a matching agents.json entry (mode, budget, auto_actions)")
        # mode/budget/allow-list init ke baad badal nahi sakte (registry gate bypass na ho)
        self.department, self.name, self._mode = department, name, mode
        self._write_budget = 0 if mode == "read_only" else write_budget
        self._auto_actions, self._tools, self.record = frozenset(auto_actions), dict(tools or {}), record
        self.reads, self.writes, self.proposals = [], [], []
        self.inputs, self.outputs, self.status = {}, {}, None

    mode = property(lambda self: self._mode)
    write_budget = property(lambda self: self._write_budget)
    auto_actions = property(lambda self: self._auto_actions)

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
            self.status = exc.reason  # with-block ke baad wala code jaan sake ki run ruka
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
        if _has_secret([args, dry_run_output, undo]):
            raise ValueError("write args/dry_run_output/undo contain a secret - tools must read credentials from env")
        self._spend()
        entry = {"action": action, "tool": tool, "args": args, "risk": risk}
        if self.mode == "shadow":
            self.writes.append({**entry, "outcome": "shadow"})
            return None
        if self.mode == "auto" and action in self.auto_actions:
            self.writes.append(entry)  # tool chalne se PEHLE gino - raise ho to bhi budget kat chuka (retry loop)
            entry["outcome"] = "error"
            result = self._tools[tool](**args)
            entry["outcome"] = "auto"
            return result
        pid = approvals.propose(self.department, self.name, action, risk, tool, args, dry_run_output, undo)
        self.proposals.append(pid)
        self.writes.append({**entry, "outcome": "proposed", "pid": pid})
        return pid

    def execute(self, pid, tool, args):
        """Founder-approved proposal chalao: wahi agent, wahi tool, wahi args (assert_executable), registry ka fn."""
        if self.mode not in ("approve", "auto"):  # shadow/read_only kabhi kuch nahi chalate
            raise ValueError(f"{self.name} is {self.mode} - execute() not allowed")
        self._check()
        self._spend()
        if approvals.get(pid)["agent"] != self.name:
            raise approvals.NotExecutable(f"{pid} belongs to another agent")
        approvals.assert_executable(pid, tool, args)
        entry = {"action": "execute", "tool": tool, "args": args, "outcome": "error", "pid": pid}
        self.writes.append(entry)  # pehle gino
        try:
            result = self._tools[tool](**args)
        except BaseException as e:  # Ctrl-C / SystemExit bhi: half-applied action approved na rahe
            # proposal band: dobara chalana = founder ka naya approval (half-applied money/stock action repeat na ho)
            approvals.mark_executed(pid, {"ok": False, "error": type(e).__name__})
            raise
        approvals.mark_executed(pid, {"ok": True})
        entry["outcome"] = "executed"
        return result


# ---------- CLI: python -m packages.core.agent kill|unkill <name|ALL> / status ----------

def _cli(argv):
    if argv[:1] == ["status"]:
        print("killed:", ", ".join(killed_agents()) or "-")
        last = {}
        for r in runs.recent(500):
            last[r["agent"]] = r
        for name, r in sorted(last.items()):
            print(f"{name:20} {r['status']:16} {r.get('mode', '-'):10} {r['at'][:16]}")
        return 0
    if len(argv) != 2 or argv[0] not in ("kill", "unkill") or not _NAME.fullmatch(argv[1]):
        print("usage: python -m packages.core.agent kill|unkill <agent-name|ALL> | status", file=sys.stderr)
        return 2
    kdir = os.path.join(_store.ops_dir(), "kill")
    os.makedirs(kdir, mode=0o700, exist_ok=True)
    path = os.path.join(kdir, argv[1])
    if argv[0] == "kill":
        os.close(os.open(path, os.O_CREAT | os.O_WRONLY, 0o600))
        print(f"killed {argv[1]} - next read/write stops it")
    elif os.path.exists(path):
        os.remove(path)
        print(f"unkilled {argv[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
