"""
deal_finder.py

Sourcing agent: roz subah pichhle 24 h ke asli deals (source price drop / restock) ka top 10, founder ke phone pe.
Spec: docs/agents/deal-finder.md. v1 = shadow mode (Agent harness): sirf digest + would-be proposals log, store
ya database mein kuch nahi badalta. Koi LLM nahi - niyam seedhe aur testable.

Usage (server; env ~/.luxella.env se, systemd unit jaisa):
    python deal_finder.py --dry-run          # sirf print (would-be writes bhi) - na ntfy, na log
    python deal_finder.py --no-push          # run log, ntfy nahi
    python deal_finder.py                    # run log + phone digest
    python deal_finder.py --eval-out x.jsonl # offline eval outputs (koi read nahi)
"""
import argparse
import json
import math
import sys
import unicodedata
from collections import Counter
from datetime import datetime, timedelta, timezone

from brand_extractor import BRAND_DISPLAY, _marketplace_slugs, display_brand

MIN_DROP, MAX_DROP = 20.0, 90.0   # < 20% = noise; >= 90% = data galti (price 0 parse), deal nahi
STALE_DAYS = 3                    # repair jaisa niyam
LIVE_BONUS = 1.2                  # store pe abhi bik sakta hai
RESTOCK_FLAT = 20.0               # restock ka discount nahi hota: MRP (compare-at) discount, warna ye
BUY_MIN_DROP = 40.0               # propose_buy: >= 40% aur jaana-maana brand site
TOP, PER_SITE, PHONE_TOP = 10, 3, 5


def clean_name(s, limit=60):
    """Zero-width / control characters hatao (scraped naamon mein milte hain), whitespace samet, 60 char."""
    text = "".join(" " if ch.isspace() else ch for ch in str(s or "")
                   if ch.isspace() or unicodedata.category(ch) not in ("Cf", "Cc"))  # newline/tab = space
    return " ".join(text.split())[:limit]


def pct_drop(old, new):
    try:
        o, n = float(old), float(new)
    except (TypeError, ValueError):
        return None
    return (o - n) / o * 100 if o > 0 else None


def precheck(change):
    """Sirf change row se jo bahar ho sakta hai (join se pehle). None = aage dekho."""
    if change["change_type"] != "price_decrease":
        return None
    drop = pct_drop(change["old_value"], change["new_value"])
    try:
        new = float(change["new_value"])
    except (TypeError, ValueError):
        return "bad_price"
    if drop is None or new <= 0 or drop >= MAX_DROP:
        return "bad_price"
    if drop < MIN_DROP:
        return "small_drop"
    return None


def _age_days(scraped_at, now):
    if not scraped_at:
        return None
    t = datetime.fromisoformat(str(scraped_at).replace("Z", "+00:00"))
    if t.tzinfo is None and now.tzinfo is not None:
        t = t.replace(tzinfo=now.tzinfo)
    return (now - t) / timedelta(days=1)


def classify(change, product, flapping_ids, now):
    """(included, reason). Naam kabhi faisla nahi badalta - sirf numbers/flags (injection se bachav)."""
    reason = precheck(change)
    if reason:
        return False, reason
    if product is None:
        return False, "no_product"
    if product.get("is_duplicate"):
        return False, "duplicate"
    age = _age_days(product.get("scraped_at"), now)
    if age is None or age > STALE_DAYS:
        return False, "stale"
    sell, landed = product.get("selling_price_inr"), product.get("landed_cost_inr")
    if not sell or not landed or float(sell) <= 0:
        return False, "no_inr"
    if float(sell) <= float(landed):
        return False, "neg_margin"
    if change.get("id") in flapping_ids:
        return False, "flapping"
    site = str(change.get("site") or "").lower()
    if site in _marketplace_slugs() and display_brand(product.get("brand"), product.get("name")) is None:
        return False, "marketplace"
    if not product.get("in_stock"):
        return False, "source_oos"
    return True, "included"


def discount(change, product):
    if change["change_type"] == "price_decrease":
        return pct_drop(change["old_value"], change["new_value"]) or 0.0
    cmp_, sell = product.get("compare_at_price_inr"), product.get("selling_price_inr")
    try:
        d = (float(cmp_) - float(sell)) / float(cmp_) * 100
    except (TypeError, ValueError, ZeroDivisionError):
        d = 0.0
    return d if d > 0 else RESTOCK_FLAT


def score(change, product):
    """discount% x log10(selling INR)^2, live pe bonus: Rs40k bag -35% (742) > Rs1.5k sock -60% (607).
    (Spec ka log10 bina square ke ulta nikla tha: 161 < 190 - test ne pakda.)"""
    s = discount(change, product) * math.log10(max(float(product["selling_price_inr"]), 10)) ** 2
    return s * LIVE_BONUS if product.get("shopify_product_id") else s


def rank(candidates, top=TOP, per_site=PER_SITE):
    """candidates: [{"change", "product", "score"}] -> top list, ek site se max per_site."""
    out, per = [], Counter()
    for c in sorted(candidates, key=lambda c: -c["score"]):
        site = c["change"].get("site")
        if per[site] < per_site:
            out.append(c)
            per[site] += 1
        if len(out) == top:
            break
    return out


def proposals_for(change, product):
    """Shadow mein log hone wale would-be actions (spec table). propose_buy kabhi auto nahi."""
    acts = []
    if product.get("shopify_product_id") and product.get("in_stock"):
        acts.append("feature_deal")
    big = change["change_type"] == "price_decrease" and discount(change, product) >= BUY_MIN_DROP
    if not product.get("shopify_product_id") or (big and str(change.get("site")).lower() in BRAND_DISPLAY):
        acts.append("propose_buy")
    return acts


def rating_buttons(day, top):
    """Har deal pe 👍/👎 (callback <= 64 bytes): d:<YYYYMMDD>:<product_id>:+|-  - bot slice 3 save karta hai."""
    tag = day.strftime("%Y%m%d")
    return [[(f"{i}. 👍", f"d:{tag}:{c['product']['id']}:+"), (f"{i}. 👎", f"d:{tag}:{c['product']['id']}:-")]
            for i, c in enumerate(top, 1)]


def margin_estimate(change, product):
    """Product ka current source price is change ke new price se alag = baad mein phir badla; INR numbers us naye
    price ke hain (db._prepare price ke saath INR bhi recompute karta hai - sync lag nahi)."""
    if change["change_type"] != "price_decrease":
        return False
    try:
        return abs(float(product.get("price")) - float(change["new_value"])) > 0.01
    except (TypeError, ValueError):
        return True


def _line(i, c):
    ch, p = c["change"], c["product"]
    name = clean_name(p.get("name") or ch.get("name"), 40)
    sell, landed = float(p["selling_price_inr"]), float(p["landed_cost_inr"])
    margin = round((sell - landed) / landed * 100)
    what = (f"-{discount(ch, p):.0f}% {ch['old_value']}->{ch['new_value']}"
            if ch["change_type"] == "price_decrease" else "restock")
    live = "live" if p.get("shopify_product_id") else "not listed"
    est = " (price changed since)" if margin_estimate(ch, p) else ""
    name = name.replace(" | ", " - ")
    return f"{i}. {ch.get('site')}: {name} · {what} · Rs{sell:,.0f} · markup {margin}%{est} · {live}"


def build_digest(top, excluded, n_changes, today):
    """(full text, phone text <= 12 lines). 0 changes = scraper shayad band - chup mat raho."""
    head = f"Luxella deals {today.isoformat()}"
    if n_changes == 0:
        msg = f"{head}: 0 changes in 24 h - scraper?"
        return msg, msg
    ex = ", ".join(f"{n} {r}" for r, n in excluded.most_common())
    full = [f"{head}: {len(top)} deals from {n_changes} changes", *[_line(i, c) for i, c in enumerate(top, 1)],
            f"excluded: {ex or '-'}"]
    phone = [f"{head}: top {min(len(top), PHONE_TOP)} of {len(top)}",
             *[_line(i, c) for i, c in enumerate(top[:PHONE_TOP], 1)],
             f"excluded: {(ex if len(ex) <= 120 else ex[:ex.rfind(', ', 0, 120)]) or '-'}"]  # poore reason pe kaato
    return "\n".join(full), "\n".join(phone[:12])


# ---------- readers (sirf padhna; ORDER BY changed_at nahi - index nahi, id se page) ----------
CHANGE_COLS = "id,site,sku,product_url,name,change_type,old_value,new_value,changed_at"
PRODUCT_COLS = ("id,site,product_url,name,brand,price,currency,in_stock,selling_price_inr,landed_cost_inr,"
                "compare_at_price_inr,shopify_product_id,is_duplicate,scraped_at")
URL_CHUNK = 50  # safe-writes <= 200; lambe URLs ke saath GET chhota rakho


def fetch_changes(client, since):
    rows, last = [], 0
    while True:
        page = (client.table("product_changes").select(CHANGE_COLS)
                .in_("change_type", ["price_decrease", "back_in_stock", "price_increase"])
                .gt("changed_at", since).gt("id", last).order("id").limit(1000).execute().data)
        rows += page
        if len(page) < 1000:
            return rows
        last = page[-1]["id"]


def fetch_products(client, keys):
    """keys: {(site, product_url)} -> {(site, url): product}. Match (site, url) se, sku se kabhi nahi."""
    out, by_site = {}, {}
    for site, url in keys:
        by_site.setdefault(site, []).append(url)
    for site, urls in by_site.items():
        for i in range(0, len(urls), URL_CHUNK):
            for p in (client.table("products").select(PRODUCT_COLS).eq("site", site)
                      .in_("product_url", urls[i:i + URL_CHUNK]).execute().data):
                out[(p["site"], p["product_url"])] = p
    return out


def latest_per_product(changes):
    """Ek product = ek row (sabse nayi decrease/restock). Flapping = uske baad usi product ka price_increase."""
    last, rises = {}, {}
    for c in sorted(changes, key=lambda c: c["id"]):
        key = (c["site"], c["product_url"])
        if c["change_type"] == "price_increase":
            rises[key] = c["id"]
        else:
            last[key] = c
    flapping = {c["id"] for key, c in last.items()
                if c["change_type"] == "price_decrease" and rises.get(key, 0) > c["id"]}
    return list(last.values()), flapping


def find_deals(changes, products, now):
    """-> (ranked top list, excluded Counter). products = fetch_products ka result."""
    rows, flapping = latest_per_product(changes)
    excluded, cands = Counter(), []
    older = sum(c["change_type"] != "price_increase" for c in changes) - len(rows)
    if older:
        excluded["older_change"] = older  # same product, newer change wins
    for c in rows:
        try:
            ok, why = classify(c, products.get((c["site"], c["product_url"])), flapping, now)
            if ok:
                p = products[(c["site"], c["product_url"])]
                cands.append({"change": c, "product": p, "score": score(c, p)})
        except (TypeError, ValueError):  # ek kharab row poora run na giraye
            ok, why = False, "bad_data"
        if not ok:
            excluded[why] += 1
    return rank(cands), excluded


# ---------- offline eval (eval_gate ke liye outputs with verdict) ----------

def eval_outputs(cases):
    out = []
    for case in cases:
        inp = case["input"]
        now = datetime.fromisoformat(inp["now"])
        if case["kind"] == "classify":
            flap = {inp["change"]["id"]} if inp.get("flapping") else set()
            ok, why = classify(inp["change"], inp.get("product"), flap, now)
            got = "included" if ok else f"excluded:{why}"
            name_ok = all(ch not in clean_name((inp.get("product") or {}).get("name") or inp["change"].get("name"))
                          for ch in ("​", "‍", "\n"))
            verdict = "pass" if got == case["expected"] and name_ok else "fail"
        else:  # rank
            cands = [{"change": c["change"], "product": c["product"], "score": score(c["change"], c["product"])}
                     for c in inp["candidates"]]
            got = [c["change"]["id"] for c in rank(cands)]
            verdict = "pass" if got == case["expected"] else "fail"
        out.append({"id": case["id"], "output": got, "verdict": verdict})
    return out


# ---------- run (Agent harness, shadow) ----------

def _deal_out(c):
    ch, p = c["change"], c["product"]
    sell, landed = float(p["selling_price_inr"]), float(p["landed_cost_inr"])
    from packages.core.agent import untrusted
    return {"product_id": p["id"], "site": ch["site"], "brand": p.get("brand"),
            "name": untrusted(clean_name(p.get("name") or ch.get("name")), ch["site"]), "change": ch["change_type"],
            "old": ch["old_value"], "new": ch["new_value"], "currency": p.get("currency"),
            "discount_pct": round(discount(ch, p), 1), "selling_inr": sell, "landed_inr": landed,
            "margin_inr": round(sell - landed), "margin_pct": round((sell - landed) / landed * 100, 1),
            "live": bool(p.get("shopify_product_id")), "score": round(c["score"], 1),
            "margin_estimate": margin_estimate(ch, p), "scraped_at": p.get("scraped_at")}


def propose(ag, c):
    """Shadow would-be writes. Args mein URL nahi (?key= jaisa URL secret check tod deta) - product_id kaafi."""
    ch, p = c["change"], c["product"]
    for act in proposals_for(ch, p):
        if act == "feature_deal":
            ag.write("feature_deal", "shopify_add_to_deals",
                     {"product_id": p["id"], "shopify_product_id": p["shopify_product_id"]}, risk="low")
        else:
            ag.write("propose_buy", "propose_purchase",
                     {"product_id": p["id"], "site": ch["site"], "new_price": ch["new_value"],
                      "currency": p.get("currency")}, risk="high")


def default_fetch(now):
    import shopify_sync
    client = shopify_sync.get_supabase()
    changes = fetch_changes(client, (now - timedelta(days=1)).isoformat())
    survivors = [c for c in latest_per_product(changes)[0] if precheck(c) is None]
    return changes, fetch_products(client, {(c["site"], c["product_url"]) for c in survivors})


def main(argv=None, fetch=None, now=None):
    ap = argparse.ArgumentParser(description="Luxella deal finder (shadow)")
    ap.add_argument("--dry-run", action="store_true", help="sirf print: na ntfy, na log")
    ap.add_argument("--no-push", action="store_true", help="run log, ntfy nahi")
    ap.add_argument("--eval-out", help="offline eval outputs likho (koi read nahi)")
    args = ap.parse_args(argv)
    if args.eval_out:
        from packages.core.eval_gate import find_cases
        with open(args.eval_out, "w") as f:
            for o in eval_outputs(find_cases("deal-finder")):
                f.write(json.dumps(o) + "\n")
        return 0
    from daily_report import gather
    from packages.core.agent import Agent, AgentStopped
    now = now or datetime.now(timezone.utc)
    fetch = fetch or (lambda: default_fetch(now))
    try:  # harness: shadow = proposals sirf log; kill switch; budget 20 (10 deals x max 2); alerts
        with Agent("sourcing", "deal-finder", mode="shadow", write_budget=20, record=not args.dry_run) as ag:
            got = gather(now, {"supabase": lambda: ag.read("supabase", fetch)})["supabase"]
            if got is None:
                ag.status = "failed"  # harness high alert; digest nahi (adhoora data pe deal galat)
                return 0
            changes, products = got
            top, excluded = find_deals(changes, products, now)
            full, phone = build_digest(top, excluded, len(changes), now.date())
            print(full + "\n---\n" + phone)
            for c in top:
                propose(ag, c)
            drops = [d for d in map(_deal_out, top) if d["change"] == "price_decrease"]
            kpis = {"new finds": len(top), "price drops caught": len(drops),
                    "buys proposed": sum(w["action"] == "propose_buy" for w in ag.writes),
                    "average discount": round(sum(d["discount_pct"] for d in drops) / len(drops), 1) if drops else None}
            if args.dry_run:
                for w in ag.writes:
                    print(f"would {w['action']}: {w['args']}")
                print("kpis:", kpis)
                return 0
            pushed = False
            if not args.no_push:
                from packages.core.approvals import push
                pushed = push(f"Luxella deals {now.date().isoformat()}", phone, tags="moneybag", card=full,
                              buttons=rating_buttons(now.date(), top))
            ag.outputs = {"changes_24h": len(changes), "top": [_deal_out(c) for c in top], "excluded": dict(excluded),
                          "kpis": kpis, "pushed": pushed}
            if not changes or (not args.no_push and not pushed):
                ag.status = "partial"
    except AgentStopped:  # kill at start: log + alert already sent
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
