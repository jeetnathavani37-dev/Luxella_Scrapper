"""
repair_variant_stock.py

Ek-baar ki repair: multi-size products ke HAR size ka Shopify stock source (Supabase
variants[].in_stock) se milao. Spec: docs/specs/2026-10-05-sync-all-sizes.md

Kyun: push per-size stock ek baar set karta tha, phir shopify_sync sirf pehla variant chhoota
tha - baad ke size badlaav Shopify tak kabhi nahi pahunche (30-product sample: 37% products
mein koi size galat, kuch sold-out sizes bik rahe the). Product-level in_stock PEHLE size se aata
hai - use KABHI target ke liye mat use karo (2026-10-05 sandal galti).

Kya karta hai (sirf last_synced_variant_stock IS NULL wale pushed multi-size products):
  - Shopify se har size ka current stock padhta hai (GraphQL, 2 products/call - cost limit)
  - target: size in_stock + price > 0 -> 10, warna 0. 1..9 (orders ke baad) ko nahi chhoota.
  - DRY RUN (default): kuch nahi likhta - totals, 20 samples, backup file
  - --confirm: CAS (changeFromQuantity) se stock set, phir product ka signature likhta hai
    (resume-able: dobara chalao to bache hue se shuru). Signature ke baad shopify_sync khud sambhalta hai.
  - Unmatched sizes (Shopify pe hai, scrape mein nahi) ko chhoota nahi; 2% se zyada -> --confirm mana (size naam mismatch).
  - Purana scrape (scraped_at > --max-age-days, default 3, ya khaali) ko BILKUL nahi chhoota - na stock, na signature.
    Wo data galat ho sakta hai (2026-10-06: 2,912 products 3-30+ din purane, zyadatar brand site se hat chuke;
    dead sites ke sizes 0 kiye gaye the - repair unhe wapas 10 kar deta). Unhe delisted-marking sambhalega.

Usage (GitHub Actions: .github/workflows/repair-variant-stock.yml):
    python repair_variant_stock.py                     # dry run, sab
    python repair_variant_stock.py --confirm --limit 5 # pehle 5 badalne wale products
    python repair_variant_stock.py --restore variant_stock_before-<run>.jsonl --confirm
    python repair_variant_stock.py --verify 30         # read-only: 30 random products ki jaanch

Requires: SUPABASE_URL, SUPABASE_SERVICE_KEY, SHOPIFY_STORE_DOMAIN, SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET
"""
import argparse
import json
import os
import random
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

import shopify_sync as ss
from shopify_push import get_size_variants

PAGE = 1000
NODES_PER_CALL = 2  # 1000-point single-query cost limit: ~300-500/product (100 variants)
MAX_UNMATCHED_SHARE = 0.02
MAX_AGE_DAYS = 3  # isse purane scrape ka size data repair ke liye bharosemand nahi
# sirf jo Shopify ne accept kiya; har run alag file (local pe pichla batch overwrite na ho)
BACKUP = os.environ.get("REPAIR_BACKUP", f"variant_stock_before-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}.jsonl")
PLAN = os.environ.get("REPAIR_PLAN", "variant_stock_plan.jsonl")         # dry run / planned (restore ke liye nahi)
REPORT = os.environ.get("REPAIR_REPORT", "variant_stock_report.json")

SIZES_QUERY = """query($ids: [ID!]!) { nodes(ids: $ids) { ... on Product { id
  variants(first: 100) { nodes { selectedOptions { name value } inventoryItem { id
    inventoryLevel(locationId: "%s") { quantities(names: ["available"]) { quantity } } } } } } } }""" % ss.LOCATION_GID


def fetch_candidates(sb):
    """Pushed, signature null, 2+ sizes - id se paged (PostgREST 1000 cap)."""
    rows, last = [], 0
    while True:
        page = (sb.table("products")
                .select("id,name,site,price,in_stock,variants,category,currency,shopify_product_id,scraped_at")
                .eq("pushed_to_shopify", True).not_.is_("shopify_product_id", "null")
                .is_("last_synced_variant_stock", "null")
                .gt("id", last).order("id").limit(PAGE).execute().data)
        rows += [r for r in page if len(get_size_variants(r)) > 1]
        if len(page) < PAGE:
            return rows
        last = page[-1]["id"]


def _scraped_at(row):
    s = row.get("scraped_at")
    if not s:
        return None
    t = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)  # naive = UTC (Supabase timestamp)


def split_fresh(rows, max_age_days=MAX_AGE_DAYS, now=None):
    """(fresh, stale). Stale = scraped_at khaali ya max_age_days se purana - in pe kuch mat likho."""
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=max_age_days)
    fresh, stale = [], []
    for r in rows:
        t = _scraped_at(r)
        (fresh if t is not None and t >= cutoff else stale).append(r)
    return fresh, stale


def shopify_sizes_bulk(token, product_ids):
    """{product_id: [{inventory_item_id, size, available}]} - option1 = size (push aise hi banata hai)."""
    out = {}
    for i in range(0, len(product_ids), NODES_PER_CALL):
        ids = [f"gid://shopify/Product/{pid}" for pid in product_ids[i:i + NODES_PER_CALL]]
        data = ss.shopify_graphql(token, SIZES_QUERY, {"ids": ids})
        for node in data["nodes"]:
            if not node:
                continue  # Shopify pe product hi nahi (pehle delete) - report mein "missing"
            pid = node["id"].rsplit("/", 1)[1]
            sizes = []
            for v in node["variants"]["nodes"]:
                level = v["inventoryItem"]["inventoryLevel"]
                sizes.append({
                    "inventory_item_id": v["inventoryItem"]["id"].rsplit("/", 1)[1],
                    "size": next((o["value"] for o in v["selectedOptions"] if o["name"].lower() == "size"),
                                 (v["selectedOptions"] or [{}])[0].get("value")),
                    "available": level["quantities"][0]["quantity"] if level else None,
                })
            out[pid] = sizes
        time.sleep(0.3)
    return out


def plan(token, rows):
    by_pid = shopify_sizes_bulk(token, [r["shopify_product_id"] for r in rows])
    items, totals = [], {"products": len(rows), "missing_on_shopify": 0, "products_changing": 0,
                         "sizes_to_0": 0, "sizes_to_10": 0, "sizes_left_1_9": 0, "unmatched_sizes": 0,
                         "sizes_checked": 0}
    for r in rows:
        shop = by_pid.get(r["shopify_product_id"])
        if shop is None:
            totals["missing_on_shopify"] += 1
            continue
        changes, skipped, unmatched = ss.size_targets(r, shop)
        totals["sizes_checked"] += len(shop)
        totals["sizes_left_1_9"] += len(skipped)
        totals["unmatched_sizes"] += len(unmatched)
        totals["sizes_to_0"] += sum(1 for _, _, t in changes if t == 0)
        totals["sizes_to_10"] += sum(1 for _, _, t in changes if t > 0)
        if changes:
            totals["products_changing"] += 1
        items.append({"row": r, "changes": changes, "unmatched": unmatched, "skipped": skipped})
    return items, totals


def _lines(it):
    for iid, current, target in it["changes"]:
        yield json.dumps({"product_id": it["row"]["shopify_product_id"], "supabase_id": it["row"]["id"],
                          "inventory_item_id": iid, "before": current, "after": target,
                          "at": datetime.now(timezone.utc).isoformat()}) + "\n"


def write_plan(items):
    with open(PLAN, "w") as f:  # har run nayi file
        for it in items:
            f.writelines(_lines(it))


def apply(sb, token, items, limit, backup_path=None):
    """Return (done, stale). Backup mein SIRF wahi sizes jo Shopify ne accept kiye (restore sahi chale)."""
    done, stale = 0, []
    with open(backup_path or BACKUP, "w") as backup:  # har run nayi file
        for it in items:
            r = it["row"]
            if it["changes"]:
                if limit and done >= limit:
                    break
                try:
                    ss.set_size_quantities(token, it["changes"], f"gid://luxella-scrapper/SizeRepair/{r['id']}")
                except ss.StaleQuantity:
                    stale.append(r["id"])  # beech mein order/badlaav - signature nahi, agle run dobara
                    continue
                backup.writelines(_lines(it))
                backup.flush()
                done += 1
                time.sleep(0.3)
            elif limit:
                continue  # --limit run: sirf badalne wale products; baaki ka signature full run mein
            sb.table("products").update({"last_synced_variant_stock": ss.stock_signature(r)}).eq("id", r["id"]).execute()
    return done, stale


def restore(token, path):
    """after -> before. Har size alag (CAS): jo beech mein badal gaye unhe chhodo, baaki wapas."""
    seen, entries = set(), []
    for line in open(path):
        if line.strip():
            e = json.loads(line)
            if e["inventory_item_id"] not in seen:  # duplicate pe pehla (sabse purana 'before') rakho
                seen.add(e["inventory_item_id"])
                entries.append(e)
    ok, stale = 0, 0
    for e in entries:
        try:
            ss.set_size_quantities(token, [(e["inventory_item_id"], e["after"], e["before"])],
                                   f"gid://luxella-scrapper/SizeRepair/restore/{e['inventory_item_id']}")
            ok += 1
        except ss.StaleQuantity:
            stale += 1
        time.sleep(0.2)
    return ok, stale


def verify(sb, token, n):
    """Read-only: n random signatured multi-size products - Shopify vs source mismatch count."""
    rows, last = [], 0
    while True:
        page = (sb.table("products").select("id,name,price,in_stock,variants,category,currency,shopify_product_id")
                .eq("pushed_to_shopify", True).not_.is_("last_synced_variant_stock", "null")
                .gt("id", last).order("id").limit(PAGE).execute().data)
        rows += page
        if len(page) < PAGE:
            break
        last = page[-1]["id"]
    sample = random.sample(rows, min(n, len(rows)))
    items, totals = plan(token, sample)
    return {"checked": len(sample), "products_mismatched": totals["products_changing"],
            "sizes_mismatched": totals["sizes_to_0"] + totals["sizes_to_10"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", action="store_true", help="asli likho (default dry run)")
    ap.add_argument("--limit", type=int, default=0, help="sirf itne badalne wale products")
    ap.add_argument("--restore", help="backup jsonl se wapas (with --confirm)")
    ap.add_argument("--verify", type=int, default=0, help="read-only jaanch, n random products")
    ap.add_argument("--max-age-days", type=float, default=MAX_AGE_DAYS,
                    help="isse purane scrape wale products chhodo (stock + signature dono)")
    args = ap.parse_args()

    sb = ss.get_supabase()
    token = ss.get_access_token()

    if args.verify:
        print(json.dumps(verify(sb, token, args.verify), indent=1))
        return
    if args.restore:
        if not args.confirm:
            n = sum(1 for line in open(args.restore) if line.strip())
            print(f"DRY RUN: {n} sizes wapas 'before' pe jaate. --confirm se chalao.")
            return
        ok, stale = restore(token, args.restore)
        print(f"restored {ok} sizes, {stale} skipped (stock beech mein badla)")
        return

    rows, stale_rows = split_fresh(fetch_candidates(sb), args.max_age_days)
    stale_sites = Counter(r["site"] for r in stale_rows).most_common(10)
    print(f"{len(rows)} multi-size products bina signature ke (scrape <= {args.max_age_days:g} din) - Shopify se padh rahe hain...")
    print(f"{len(stale_rows)} purane scrape wale chhode (kuch nahi likhega): {stale_sites}")
    items, totals = plan(token, rows)
    totals["skipped_stale"] = len(stale_rows)
    unmatched_share = totals["unmatched_sizes"] / max(1, totals["sizes_checked"])
    totals["unmatched_share"] = round(unmatched_share, 4)
    samples = [{"id": it["row"]["id"], "site": it["row"]["site"], "name": it["row"]["name"],
                "changes": [{"item": i, "from": c, "to": t} for i, c, t in it["changes"]],
                "unmatched": it["unmatched"]} for it in items if it["changes"]][:20]
    json.dump({"totals": totals, "samples": samples}, open(REPORT, "w"), indent=1)
    print(json.dumps(totals, indent=1))
    for s in samples[:20]:
        print(f"  {s['site']:16} {s['name'][:40]:40} " + ", ".join(f"{c['from']}->{c['to']}" for c in s["changes"]))
    write_plan([it for it in items if it["changes"]])
    print(f"plan: {PLAN}  report: {REPORT}")

    if not args.confirm:
        print("DRY RUN - kuch nahi likha. --confirm (aur pehle --limit 5) se chalao.")
        return
    if unmatched_share > MAX_UNMATCHED_SHARE:
        print(f"ABORT: {unmatched_share:.1%} sizes unmatched (> {MAX_UNMATCHED_SHARE:.0%}) - size naam mismatch? Kuch nahi likha.")
        sys.exit(1)
    done, stale = apply(sb, token, items, args.limit)
    print(f"APPLIED: {done} products ke sizes badle" + (f" (limit {args.limit})" if args.limit else "")
          + f"; {len(stale)} stale (agle run): {stale[:20]}  backup: {BACKUP}")


if __name__ == "__main__":
    main()
