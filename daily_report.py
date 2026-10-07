"""
daily_report.py

Roz subah ki Luxella health report (spec: docs/specs/2026-10-07-daily-report-agent.md).
Read-only: Supabase/Shopify/GitHub sirf padhta hai, kahin likhta nahi. Koi LLM nahi - har number
isi run ki query se (kpi-report skill).

Slice 1: report ka hisaab (status, 7-day avg, text, phone message). Readers + main() slice 2 mein.

`data` ka shape - har source ya to dict ya None (= source missing, line pe "n/a"):
    supabase:  {pushed, live, oos, price0, stale3d, scraped_24h, changes_24h}
    shopify:   {active, oos_live}
    actions:   {failed: [{name, url}], cancelled, success, running}
    approvals: {count, top: [str]}
    at:        {source: iso time}  (Data line ke liye)
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta

NA = "n/a (source missing)"
SOURCES = ("supabase", "shopify", "actions", "approvals")
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
        ("OOS-but-live", _get(data, "shopify", "oos_live"), 0),
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
    if price0:  # live products price 0 pe = paise ka nuksaan (PR #15/#16), target 0
        bad.append(f"price 0 live: {_fmt(price0)} (target 0)")
    info = [f"stale > 3 d: {_fmt(stale)}"]
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
        return "\n".join([f"Luxella {today.isoformat()}: sab theek", *info[:1],
                          f"approvals pending: {appr['count'] if appr else 0}"])
    lines = [f"Luxella {today.isoformat()}: {len(bad) + len(failed)} problem(s)", *bad]
    lines += [f"FAILED {f['name']}" for f in failed]
    lines += [f"{s}: {NA}" for s in missing]
    lines += info
    if appr:
        lines.append(f"approvals pending: {appr['count']}")
    if len(lines) > SHORT_MAX_LINES:
        lines = lines[:SHORT_MAX_LINES - 1] + ["... poori report: agent_runs log"]
    return "\n".join(lines)


if __name__ == "__main__":  # slice 2: readers + flags
    sample = {"supabase": {"pushed": 49518, "live": 31306, "oos": 18212, "price0": 237, "stale3d": 9875,
                           "scraped_24h": 46025, "changes_24h": 1638},
              "shopify": None, "actions": {"failed": [], "cancelled": 7, "success": 20, "running": 1},
              "approvals": {"count": 0, "top": []}, "at": {}}
    r = build_report(sample, [], datetime.now())
    print(r.text, "\n---\n" + r.short)
