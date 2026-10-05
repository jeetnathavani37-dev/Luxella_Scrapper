"""Eval gate (eval-gate skill). Run before ANY prompt or tool change to a department agent.

Cases: departments/*/evals/<agent>.jsonl, one JSON per line:
    {"id": "1", "input": "...", "expected": "...", "pass_rule": "...", "critical": false}
("critical" is optional, default false.)

Outputs: the agent is run on every case in dry-run / read-only mode and its answers saved as JSONL:
    {"id": "1", "output": "..."}                       # graded by --judge gemini
    {"id": "1", "output": "...", "verdict": "pass"}    # already graded (manual / offline)

    .venv/bin/python -m packages.core.eval_gate curator --outputs runs/curator.jsonl
    .venv/bin/python -m packages.core.eval_gate curator --outputs runs/curator.jsonl --judge gemini
    .venv/bin/python -m packages.core.eval_gate --selftest

Gate: pass rate >= 90% AND no critical case that passed in the previous result now fails (and no critical
case missing an output). Writes evals/results/<agent>-<UTC time>.json (gitignored), prints a table,
exits 1 when the gate fails. Gemini judge uses the free key GEMINI_API_KEY (by name only), results cached.
"""
import argparse
import glob
import hashlib
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PASS_RATE = 0.90
GEMINI_MODEL = os.environ.get("EVAL_GEMINI_MODEL", "gemini-3.5-flash-lite")
CACHE = os.path.join(REPO, "evals", "results", ".judge_cache.json")


def load_jsonl(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def find_cases(agent, repo=REPO):
    hits = glob.glob(os.path.join(repo, "departments", "*", "evals", f"{agent}.jsonl"))
    if not hits:
        raise SystemExit(f"no eval file departments/*/evals/{agent}.jsonl")
    return load_jsonl(hits[0])


def judge_gemini(case, output, cache):
    key = hashlib.sha256(json.dumps([case, output], sort_keys=True).encode()).hexdigest()
    if key in cache:
        return cache[key]
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY not set - grade offline (verdict in outputs) or set the key")
    prompt = ("You grade an AI agent's answer against a rule. Reply with JSON only: "
              '{"verdict":"pass"|"fail","reason":"<one line>"}.\n'
              f"Situation: {case['input']}\nExpected behaviour: {case['expected']}\n"
              f"Pass rule: {case['pass_rule']}\nAgent answer: {output}")
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        data=json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                         "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key}, method="POST")
    body = json.loads(urllib.request.urlopen(req, timeout=60).read())
    result = json.loads(body["candidates"][0]["content"]["parts"][0]["text"])
    cache[key] = {"verdict": result["verdict"], "reason": result.get("reason", "")}
    return cache[key]


def previous_result(agent, results_dir):
    """Latest GREEN run of exactly this agent - a failed run is never the baseline (warna dobara chalane se
    critical regression chhup jaata)."""
    for path in sorted(glob.glob(os.path.join(results_dir, f"{agent}-*.json")), reverse=True):
        rep = json.load(open(path))
        if rep.get("agent") == agent and rep.get("gate") == "pass":
            return rep
    return None


def run_gate(agent, cases, outputs, judge=None, results_dir=None):
    results_dir = results_dir or os.path.join(REPO, "evals", "results")
    os.makedirs(results_dir, exist_ok=True)
    by_id = {str(o["id"]): o for o in outputs}
    cache = json.load(open(CACHE)) if judge and os.path.exists(CACHE) else {}
    rows = []
    for c in cases:
        o = by_id.get(str(c["id"]))
        if o is None:
            rows.append({"id": c["id"], "verdict": "fail", "reason": "no output", "critical": bool(c.get("critical"))})
            continue
        if "verdict" in o:
            g = {"verdict": o["verdict"], "reason": o.get("reason", "")}
        elif judge == "gemini":
            g = judge_gemini(c, o["output"], cache)
        else:
            raise SystemExit(f"case {c['id']}: no verdict and no --judge")
        rows.append({"id": c["id"], **g, "critical": bool(c.get("critical"))})
    if judge:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        json.dump(cache, open(CACHE, "w"))

    passed = sum(r["verdict"] == "pass" for r in rows)
    rate = passed / len(rows) if rows else 0.0
    prev = previous_result(agent, results_dir)
    prev_pass = {str(r["id"]) for r in (prev or {}).get("rows", []) if r["verdict"] == "pass"}
    critical_regressions = [r["id"] for r in rows if r["critical"] and r["verdict"] != "pass"
                            and (str(r["id"]) in prev_pass or r["reason"] == "no output")]
    ok = rate >= PASS_RATE and not critical_regressions
    report = {"agent": agent, "at": datetime.now(timezone.utc).isoformat(), "cases": len(rows), "passed": passed,
              "pass_rate": round(rate, 3), "critical_regressions": critical_regressions, "gate": "pass" if ok else "fail",
              "rows": rows}
    out = os.path.join(results_dir, f"{agent}-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%f}.json")
    json.dump(report, open(out, "w"), indent=1)
    return report, out


def print_report(report):
    for r in report["rows"]:
        mark = "PASS" if r["verdict"] == "pass" else "FAIL"
        print(f"  {mark}  {r['id']:>4}{' (critical)' if r['critical'] else ''}  {r.get('reason', '')[:80]}")
    print(f"{report['agent']}: {report['passed']}/{report['cases']} = {report['pass_rate']:.0%}, "
          f"critical regressions {report['critical_regressions'] or 'none'} -> GATE {report['gate'].upper()}")


def _selftest():
    import tempfile
    tmp = tempfile.mkdtemp()
    cases = [{"id": str(i), "input": "x", "expected": "y", "pass_rule": "z", "critical": i == 1} for i in range(1, 11)]
    nine = [{"id": str(i), "output": "o", "verdict": "pass" if i != 10 else "fail"} for i in range(1, 11)]
    rep, _ = run_gate("t", cases, nine, results_dir=tmp)
    assert rep["gate"] == "pass" and rep["pass_rate"] == 0.9, rep
    eight = [{"id": str(i), "output": "o", "verdict": "pass" if i < 9 else "fail"} for i in range(1, 11)]
    rep, _ = run_gate("t", cases, eight, results_dir=tmp)
    assert rep["gate"] == "fail", rep
    # critical case 1 passed before, fails now -> gate fails even at 90%
    crit = [{"id": str(i), "output": "o", "verdict": "pass" if i != 1 else "fail"} for i in range(1, 11)]
    run_gate("t", cases, nine, results_dir=tmp)
    rep, _ = run_gate("t", cases, crit, results_dir=tmp)
    assert rep["gate"] == "fail" and rep["critical_regressions"] == ["1"], rep
    rep, _ = run_gate("t", cases, crit, results_dir=tmp)  # same bad output dobara -> phir bhi fail
    assert rep["gate"] == "fail", "re-run hid a critical regression"
    run_gate("t-v2", cases, eight, results_dir=tmp)       # prefix wala doosra agent baseline nahi banta
    rep, _ = run_gate("t", cases, crit, results_dir=tmp)
    assert rep["gate"] == "fail", rep
    print("eval_gate selftest ok")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("agent", nargs="?")
    ap.add_argument("--outputs", help="JSONL of {id, output[, verdict, reason]}")
    ap.add_argument("--judge", choices=["gemini"])
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest()
        return
    if not a.agent or not a.outputs:
        ap.error("agent and --outputs are required")
    report, path = run_gate(a.agent, find_cases(a.agent), load_jsonl(a.outputs), judge=a.judge)
    print_report(report)
    print(f"saved {os.path.relpath(path, REPO)}")
    sys.exit(0 if report["gate"] == "pass" else 1)


if __name__ == "__main__":
    main()
