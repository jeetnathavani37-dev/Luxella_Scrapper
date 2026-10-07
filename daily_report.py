"""
daily_report.py

Roz subah ki Luxella health report (spec: docs/specs/2026-10-07-daily-report-agent.md).
Read-only: Supabase/Shopify/GitHub sirf padhta hai, kahin likhta nahi. Koi LLM nahi - har number
isi run ki query se (kpi-report skill).

Usage (server; env ~/.luxella.env se, systemd unit jaisa):
    python daily_report.py --dry-run   # sirf print - na ntfy, na snapshot, na log
    python daily_report.py --no-push   # snapshot + agent_runs log, ntfy nahi
    python daily_report.py             # sab + phone pe ntfy

`data` ka shape - har source ya to dict ya None (= source missing, line pe "n/a"):
    supabase:  {pushed, live, oos, price0, stale3d, scraped_24h, changes_24h}
    shopify:   {active, oos_live}
    actions:   {failed: [{name, url}], cancelled, success, running}
    approvals: {count, top: [str]}
    at:        {source: iso time}  (Data line ke liye)
"""
import argparse
import json
import os
import sys
import time
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

NA = "n/a (source missing)"
SNAP_FILE = "daily_report.jsonl"
DEFAULT_TOKEN_FILE = "/root/.config/agent-keys/github-luxella-token"
DEFAULT_REPO = "jeetnathavani37-dev/Luxella_Scrapper"
RETRY_SLEEP = 10
SOURCES = ("supabase", "shopify", "actions", "approvals", "ports")
SHORT_MAX_LINES = 12


@dataclass
class Report:
    text: str        # poori report (log + terminal)
    short: str       # phone (ntfy), <= 12 lines
    status: str      # ok / partial / failed  (log_run status)
    priority: str    # "high" agar kuch bad, warna "default"
    snapshot: dict   # daily_report.jsonl line (id zaroori - _store.read_all bina id ki line chhod deta hai)


def kpi_status(value, target):
    """ok / bad / '-' (koi target nahi) / NA. Target sab 0 hain (<= 0 = ok), isliye 'watch' abhi nahi.
    ponytail: watch tab jodo jab koi non-zero target aaye."""
    if value is None:
        return NA
    if target is None:
        return "-"
    return "ok" if value <= target else "bad"


def seven_day_avg(history, key, today):
    """Pichhle 7 din (aaj chhod ke) ka average; har din ki latest snapshot. 7 din pure na hon to None."""
    per_day = {}
    for snap in sorted(history, key=lambda s: s.get("at", "")):
        d = date.fromisoformat(snap["at"][:10])
        if today - timedelta(days=7) <= d < today:
            per_day[d] = snap.get("kpis", {}).get(key)
    vals = [v for v in per_day.values() if v is not None]
    if len(per_day) < 7 or not vals:
        return None
    return sum(vals) / len(vals)


def _get(data, source, key):
    src = data.get(source)
    return None if src is None else src.get(key)


def _kpis(data):
    """(naam, value, target) - catalog department ke 5 KPI (departments/catalog/README.md)."""
    actions = data.get("actions")
    return [
        ("products live", _get(data, "supabase", "live"), None),
        # target nahi (founder 2026-10-07, option a): sold-out listings SEO ke liye live rehti hain - info, alert nahi
        ("OOS-but-live", _get(data, "shopify", "oos_live"), None),
        ("synced today", _get(data, "supabase", "changes_24h"), None),
        ("failed syncs", None if actions is None else len(actions["failed"]), 0),
        ("photo quality score", None, None),  # abhi koi source nahi
    ]


def _fmt(v):
    if v is None:
        return NA
    return f"{v:,.0f}" if isinstance(v, (int, float)) else str(v)


def build_report(data, history, now):
    today = now.date()
    rows, bad = [], []
    for name, value, target in _kpis(data):
        status = kpi_status(value, target)
        avg = seven_day_avg(history, name, today)
        rows.append(f"{name} | {_fmt(value)} | {'-' if avg is None else _fmt(avg)} | "
                    f"{'-' if target is None else f'<= {target}'} | {status}")
        if status == "bad":
            bad.append(f"{name}: {_fmt(value)} (target <= {target})")

    price0, stale = _get(data, "supabase", "price0"), _get(data, "supabase", "stale3d")
    public = _get(data, "ports", "public")
    if public:  # server hardening spec: sirf :22 bahar khula ho; koi aur = app galti se internet pe
        bad.append("public ports: " + ", ".join(public) + " (only 22 allowed)")
    if price0:  # live products price 0 pe = paise ka nuksaan (PR #15/#16), target 0
        bad.append(f"price 0 live: {_fmt(price0)} (target 0)")
    info = [f"stale > 3 d: {_fmt(stale)}"]
    if data.get("killed"):  # bhoola hua kill switch roz dikhe (spec risk)
        info.append("killed agents: " + ", ".join(data["killed"]))
    actions = data.get("actions")
    failed = [] if actions is None else actions["failed"]
    if actions is not None and actions.get("cancelled"):
        info.append(f"cancelled jobs (24 h): {actions['cancelled']}")
    appr = data.get("approvals")

    lines = [f"Catalog · {today.isoformat()} · lead daily-report",
             "KPI | today | 7-day avg | target | status", *rows,
             "Highlights: " + ("; ".join(bad + info) if bad else "; ".join(info))]
    lines += [f"FAILED: {f['name']} - {f['url']}" for f in failed]
    lines.append(NA if appr is None else
                 f"Needs founder: {appr['count']} pending approvals"
                 + (" - top 3: " + "; ".join(appr["top"][:3]) if appr["top"] else ""))
    at = data.get("at", {})
    lines.append("Data: " + ", ".join(f"{s} @ {at.get(s, '-')}" if data.get(s) is not None else f"{s} {NA}"
                                       for s in SOURCES))

    missing = [s for s in SOURCES if data.get(s) is None]
    status = "failed" if len(missing) == len(SOURCES) else "partial" if missing else "ok"
    snapshot = {"id": f"d-{now.strftime('%Y-%m-%dT%H:%M')}", "at": now.isoformat(), "status": status,
                "kpis": {name: value for name, value, _ in _kpis(data)}}
    return Report(text="\n".join(lines), short=short_message(today, bad, failed, info, missing, appr),
                  status=status, priority="high" if bad or failed else "default", snapshot=snapshot)


def short_message(today, bad, failed, info, missing, appr):
    """Phone ke liye: bad pehle, max 12 lines. Sab theek ho to 3 lines."""
    if not bad and not failed and not missing:
        return "\n".join([f"Luxella {today.isoformat()}: sab theek", *info,
                          f"approvals pending: {appr['count'] if appr else 0}"])
    lines = [f"Luxella {today.isoformat()}: {len(bad) + len(missing)} problem(s)", *bad]  # failed already in bad
    by_name = Counter(f["name"] for f in failed)  # ek workflow = ek line (x2, x3...)
    lines += [f"FAILED {n}" + (f" x{c}" if c > 1 else "") for n, c in by_name.items()]
    lines += [f"{s}: {NA}" for s in missing]
    lines += info
    if appr:
        lines.append(f"approvals pending: {appr['count']}")
    if len(lines) > SHORT_MAX_LINES:
        lines = lines[:SHORT_MAX_LINES - 1] + ["... poori report: agent_runs log"]
    return "\n".join(lines)


# ---------- readers (sirf padhna) ----------

def read_supabase(client, now):
    """Exact counts; ORDER BY nahi (scraped_at/changed_at pe index nahi - safe-writes)."""
    d1, d3 = (now - timedelta(days=1)).isoformat(), (now - timedelta(days=3)).isoformat()

    def n(q):
        return q.execute().count

    def products():
        return client.table("products").select("id", count="exact").limit(1)

    def pushed():
        return products().not_.is_("shopify_product_id", "null")

    return {"pushed": n(pushed()), "live": n(pushed().eq("in_stock", True)),
            "oos": n(pushed().eq("in_stock", False)), "price0": n(pushed().or_("price.is.null,price.eq.0")),
            "stale3d": n(pushed().lt("scraped_at", d3)), "scraped_24h": n(products().gt("scraped_at", d1)),
            "changes_24h": n(client.table("product_changes").select("id", count="exact").limit(1)
                             .gt("changed_at", d1))}


SHOPIFY_COUNTS = """{ active: productsCount(query: "status:active", limit: null) { count precision }
  oos_live: productsCount(query: "status:active inventory_total:<=0", limit: null) { count precision } }"""


def read_shopify(token):
    """limit: null - warna count 10,000 pe ruk jaata hai (live ~50k). Read retry = PR #33."""
    from repair_variant_stock import read_graphql
    data = read_graphql(token, SHOPIFY_COUNTS, {})
    if any(data[k]["precision"] != "EXACT" for k in ("active", "oos_live")):
        raise RuntimeError("productsCount not EXACT")
    return {"active": data["active"]["count"], "oos_live": data["oos_live"]["count"]}


def read_actions(token_file, repo, since):
    """Pichhle 24 h ke runs: failed (naam + link), cancelled, success, running. Token kabhi print nahi."""
    with open(token_file) as f:
        token = f.read().strip()
    runs, page = [], 1
    while True:
        url = (f"https://api.github.com/repos/{repo}/actions/runs?per_page=100&page={page}"
               f"&created=>={since.strftime('%Y-%m-%dT%H:%M:%SZ')}")
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}",
                                                   "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            batch = json.load(r)["workflow_runs"]
        runs += batch
        if len(batch) < 100 or page == 5:  # ponytail: 500 runs/din cap, abhi ~32
            break
        page += 1
    return {"failed": [{"name": r["name"], "url": r["html_url"]} for r in runs if r["conclusion"] == "failure"],
            "cancelled": sum(r["conclusion"] == "cancelled" for r in runs),
            "success": sum(r["conclusion"] == "success" for r in runs),
            "running": sum(r["conclusion"] is None for r in runs)}


def public_listeners(ss_output):
    """`ss -ltnH` ke local addresses mein se jo localhost pe nahi aur :22 nahi. Docker ufw bypass karta hai
    (docker-proxy 0.0.0.0:<port> pe sunta hai) - aisa koi bhi port yahan dikh jaata hai."""
    out = set()
    for line in ss_output.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        host, _, port = parts[3].rpartition(":")
        host = host.split("%")[0].strip("[]")
        if port != "22" and not (host.startswith("127.") or host == "::1"):
            out.add(f"{host or '*'}:{port}")
    return sorted(out)


def read_ports():
    import subprocess
    run = subprocess.run(["ss", "-ltnH"], capture_output=True, text=True, timeout=10, check=True)
    if not any(line.split()[3].endswith(":22") for line in run.stdout.splitlines() if len(line.split()) > 3):
        raise RuntimeError("no :22 listener seen - ss output not trustworthy")  # khaali output "saaf" na lage
    # ponytail: TCP only, and relies on docker-proxy (default userland-proxy) showing published ports in ss;
    # if daemon.json ever sets "userland-proxy": false, add a `docker ps` port check here.
    return {"public": public_listeners(run.stdout)}


def read_approvals():
    from packages.core.approvals import list_pending
    pending = list_pending()
    return {"count": len(pending), "top": [f"{p['id']} {str(p.get('action', ''))[:60]}" for p in pending[:3]]}


def gather(now, readers):
    """Har source alag; ek fail ho to None (report phir bhi jaati hai). Error ka sirf type log - values nahi."""
    data, at = {}, {}
    for name, fn in readers.items():
        data[name] = None
        for attempt in (1, 2):  # ek baar dobara: 2026-10-07 dry-run mein Supabase count ek baar APIError, phir theek
            try:
                data[name] = fn()
                at[name] = datetime.now(timezone.utc).strftime("%H:%M UTC")
                break
            except Exception as e:
                print(f"[daily_report] {name} failed ({attempt}/2): {type(e).__name__}", file=sys.stderr)
                if attempt == 1:
                    time.sleep(RETRY_SLEEP)
    data["at"] = at
    return data


def default_readers(now):
    def supabase():
        import shopify_sync
        return read_supabase(shopify_sync.get_supabase(), now)

    def shopify():
        import shopify_sync
        return read_shopify(shopify_sync.get_access_token())

    def actions():
        return read_actions(os.environ.get("GITHUB_TOKEN_FILE", DEFAULT_TOKEN_FILE),
                            os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPO), now - timedelta(days=1))

    return {"supabase": supabase, "shopify": shopify, "actions": actions, "approvals": read_approvals,
            "ports": read_ports}


def main(argv=None, readers=None, now=None):
    ap = argparse.ArgumentParser(description="Luxella daily report (read-only)")
    ap.add_argument("--dry-run", action="store_true", help="sirf print: na ntfy, na snapshot, na log")
    ap.add_argument("--no-push", action="store_true", help="snapshot + log, ntfy nahi")
    args = ap.parse_args(argv)
    from packages.core import _store
    from packages.core.agent import Agent, AgentStopped, killed_agents
    now = now or datetime.now(timezone.utc)
    try:  # harness: kill switch, run log, failure alert (spec 2026-10-07-agent-standard). Read-only, budget 0.
        with Agent("catalog", "daily-report", mode="read_only", record=not args.dry_run) as ag:
            data = gather(now, {n: (lambda n=n, fn=fn: ag.read(n, fn))
                                for n, fn in (readers or default_readers(now)).items()})
            data["killed"] = killed_agents()
            report = build_report(data, _store.read_all(_store.path_for(SNAP_FILE)), now)
            print(report.text + "\n---\n" + report.short)
            if args.dry_run:
                return 0
            _store.append(_store.path_for(SNAP_FILE), report.snapshot)
            pushed = False
            if not args.no_push:
                from packages.core.approvals import push
                pushed = push(f"Luxella daily {now.date().isoformat()}", report.short, priority=report.priority,
                              tags="warning" if report.priority == "high" else "white_check_mark")
            ag.inputs = {"flags": [a for a in ("no_push",) if getattr(args, a)]}
            ag.outputs = {"kpis": report.snapshot["kpis"], "pushed": pushed}
            ag.status = report.status
    except AgentStopped:  # kill switch at start: log + alert already sent; exit 0 so systemd doesn't flap
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
