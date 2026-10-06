"""
relist_sizes.py

Ek-baar ka kaam: jo products Shopify pe BINA SIZE ke list hue (sirf 1 "Default Title" variant) jabki source
pe 2+ sizes hain, unme asli Size variants jodo. Spec: docs/specs/2026-10-06-relist-sizeless-products.md

Kyun (2026-10-06): 3,567 live products aise - 2,312 bina size chune kharide ja sakte the, 975 "sold out"
dikh rahe the jabki sizes available the (stock pehle size se aata tha). Push 2026-08-30..09-14 ke beech hue
(size data tab nahi tha); uske baad ke push sahi hain - ye sirf backfill hai.

Sequence (2026-10-06 ko draft test products pe aazmaya, phir delete):
  1. productOptionsCreate(Size = saare sizes, LEAVE_AS_IS) -> purana "Default Title" variant PEHLA size ban
     jaata hai, wahi variant id + inventory item (carts nahi tootte, Supabase ids nahi badalti)
  2. productVariantsBulkCreate(baaki sizes: price, MRP, SKU, tracked, stock 10/0 creation pe hi)
  3. pehla variant: price/MRP/SKU update + stock CAS (agar target alag)
  4. Supabase: last_synced_variant_stock = signature -> ab shopify_sync har size khud sahi rakhta hai
Undo (--restore): productOptionsDelete(Size, POSITION) -> baaki sizes hat-te, original wapas "Default Title"
(wahi id); phir price/SKU/stock backup se, signature null. (Ye bhi test product pe aazmaya.)

Target = shopify_push.get_size_variants (naye push jaisa price/SKU) + shopify_sync rule (size in_stock + price>0
-> 10, warna 0) - taaki agla sync kuch na badle.

Usage (GitHub Actions: .github/workflows/relist-sizes.yml):
    python relist_sizes.py                          # dry run: counts + 20 samples, kuch nahi likhta
    python relist_sizes.py --confirm --limit 1      # pehla product
    python relist_sizes.py --confirm --only-id 3860 # ek specific Supabase product (jaise ALO Runner)
    python relist_sizes.py --restore relist_before-<run>.jsonl --confirm

Requires: SUPABASE_URL, SUPABASE_SERVICE_KEY, SHOPIFY_STORE_DOMAIN, SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET
"""
import argparse
import json
import os
import time
from collections import Counter
from datetime import datetime, timezone

import repair_variant_stock as rv
import shopify_sync as ss
from shopify_push import get_size_variants

NODES_PER_CALL = 25  # single-variant products - sasta query
BACKUP = os.environ.get("RELIST_BACKUP", f"relist_before-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}.jsonl")
REPORT = os.environ.get("RELIST_REPORT", "relist_report.json")

READ_QUERY = """query($ids: [ID!]!) { nodes(ids: $ids) { ... on Product { id
  options { id name }
  variants(first: 2) { nodes { id title price compareAtPrice inventoryItem { id sku
    inventoryLevel(locationId: "%s") { quantities(names: ["available"]) { quantity } } } } } } } }""" % ss.LOCATION_GID

OPTIONS_CREATE = """mutation($productId: ID!, $options: [OptionCreateInput!]!) {
  productOptionsCreate(productId: $productId, options: $options, variantStrategy: LEAVE_AS_IS) {
    product { options { id name } variants(first: 2) { nodes { id title } } } userErrors { field message code } } }"""
VARIANTS_CREATE = """mutation($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
  productVariantsBulkCreate(productId: $productId, variants: $variants) {
    productVariants { id title } userErrors { field message code } } }"""
VARIANTS_UPDATE = """mutation($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
  productVariantsBulkUpdate(productId: $productId, variants: $variants) {
    productVariants { id } userErrors { field message code } } }"""
OPTIONS_DELETE = """mutation($productId: ID!, $options: [ID!]!) {
  productOptionsDelete(productId: $productId, options: $options, strategy: POSITION) {
    product { options { name } variants(first: 2) { nodes { id title } } } userErrors { field message code } } }"""


class RelistError(Exception):
    """Shopify ne mana kiya - run yahin roko (fail-fast), backup + report dekho."""


def _gql(token, query, variables, key):
    data = ss.shopify_graphql(token, query, variables)[key]
    errs = data.get("userErrors") or []
    if errs:
        raise RelistError(f"{key}: {errs[:3]}")
    return data


def build_targets(row):
    """[{size, sku, price, compare_at, qty}] - naye push jaisa (get_size_variants) + sync ka stock rule.
    [] = relist nahi (single size / price 0)."""
    if not ss._price_ok(row):
        return []
    out, seen = [], set()
    for sv in get_size_variants(row):
        size = str(sv["size"]).strip()  # sync bhi stripped size se match karta hai
        if not size or size in seen:
            continue
        seen.add(size)
        out.append({
            "size": size,
            "sku": sv.get("sku") or f"LX-{row['id']}-{size}",
            "price": str(sv["selling_price_inr"]),
            "compare_at": str(sv["compare_at_price_inr"]) if sv.get("compare_at_price_inr") else None,
            "qty": ss.SIZE_IN_STOCK_QTY if sv["in_stock"] else 0,
        })
    return out if len(out) > 1 else []


def read_shopify(token, product_ids):
    """{product_id: {options, variants[...]}} - sirf wahi jinka Shopify pe EXACTLY 1 variant hai."""
    out = {}
    for i in range(0, len(product_ids), NODES_PER_CALL):
        ids = [f"gid://shopify/Product/{p}" for p in product_ids[i:i + NODES_PER_CALL]]
        for node in ss.shopify_graphql(token, READ_QUERY, {"ids": ids})["nodes"]:
            if not node or len(node["variants"]["nodes"]) != 1:
                continue
            v = node["variants"]["nodes"][0]
            lvl = v["inventoryItem"]["inventoryLevel"]
            out[node["id"].rsplit("/", 1)[1]] = {
                "options": node["options"],
                "variant_id": v["id"], "title": v["title"], "price": v["price"],
                "compare_at": v["compareAtPrice"], "sku": v["inventoryItem"]["sku"],
                "inventory_item_id": v["inventoryItem"]["id"].rsplit("/", 1)[1],
                "available": lvl["quantities"][0]["quantity"] if lvl else None,
            }
        time.sleep(0.3)
    return out


def plan(token, rows):
    shop = read_shopify(token, [str(r["shopify_product_id"]) for r in rows])
    items, totals = [], Counter(candidates=len(rows))
    for r in rows:
        s = shop.get(str(r["shopify_product_id"]))
        if s is None:
            totals["not_single_variant_on_shopify"] += 1  # pehle se sizes hain / product nahi mila
            continue
        if s["title"] != "Default Title":
            totals["skipped_not_default_title"] += 1  # adhoora pichla run / haath se badla - insaan dekhe
            continue
        targets = build_targets(r)
        if not targets:
            totals["skipped_no_targets"] += 1
            continue
        totals["to_relist"] += 1
        totals["variants_to_create"] += len(targets) - 1
        totals["sizes_in_stock"] += sum(t["qty"] > 0 for t in targets)
        if (s["available"] or 0) == 0 and any(t["qty"] > 0 for t in targets):
            totals["sold_out_becomes_buyable"] += 1
        items.append({"row": r, "shop": s, "targets": targets})
    return items, dict(totals)


def relist_one(sb, token, it, backup):
    r, s, t = it["row"], it["shop"], it["targets"]
    pid = f"gid://shopify/Product/{r['shopify_product_id']}"
    backup.write(json.dumps({"supabase_id": r["id"], "product_id": r["shopify_product_id"], "before": s,
                             "targets": t, "at": datetime.now(timezone.utc).isoformat()}) + "\n")
    backup.flush()  # backup PEHLE, phir koi write
    res = _gql(token, OPTIONS_CREATE, {"productId": pid, "options": [
        {"name": "Size", "values": [{"name": x["size"]} for x in t]}]}, "productOptionsCreate")
    first = res["product"]["variants"]["nodes"][0]
    if first["id"] != s["variant_id"] or first["title"] != t[0]["size"]:
        raise RelistError(f"{r['id']}: unexpected first variant {first} (expected {s['variant_id']} as {t[0]['size']})")
    _gql(token, VARIANTS_CREATE, {"productId": pid, "variants": [{
        "optionValues": [{"optionName": "Size", "name": x["size"]}], "price": x["price"],
        "compareAtPrice": x["compare_at"], "inventoryItem": {"tracked": True, "sku": x["sku"]},
        "inventoryPolicy": "DENY",
        "inventoryQuantities": [{"locationId": ss.LOCATION_GID, "availableQuantity": x["qty"]}]} for x in t[1:]]},
        "productVariantsBulkCreate")
    _gql(token, VARIANTS_UPDATE, {"productId": pid, "variants": [{
        "id": s["variant_id"], "price": t[0]["price"], "compareAtPrice": t[0]["compare_at"],
        "inventoryItem": {"sku": t[0]["sku"]}}]}, "productVariantsBulkUpdate")
    if s["available"] != t[0]["qty"]:
        ss.set_size_quantities(token, [(s["inventory_item_id"], s["available"] or 0, t[0]["qty"])],
                               f"gid://luxella-scrapper/Relist/{r['id']}")
    sb.table("products").update({"last_synced_variant_stock": ss.stock_signature(r)}).eq("id", r["id"]).execute()


def apply(sb, token, items, limit, backup_path=None):
    done = 0
    with open(backup_path or BACKUP, "a") as backup:
        for it in items:
            if limit and done >= limit:
                break
            relist_one(sb, token, it, backup)  # RelistError -> run rukta hai (fail-fast)
            done += 1
            print(f"  [RELISTED] {it['row']['site']:14} {it['row']['name'][:40]:40} {len(it['targets'])} sizes")
            time.sleep(0.5)
    return done


def restore(sb, token, path):
    """Backup se: Size option hatao (POSITION -> original variant wapas 'Default Title'), price/SKU/stock wapas,
    signature null. Wahi product jo backup mein hai."""
    ok = 0
    for line in open(path):
        if not line.strip():
            continue
        e = json.loads(line)
        pid, before = f"gid://shopify/Product/{e['product_id']}", e["before"]
        node = ss.shopify_graphql(token, READ_QUERY.replace("variants(first: 2)", "variants(first: 100)"),
                                  {"ids": [pid]})["nodes"][0]
        size_opt = [o["id"] for o in node["options"] if o["name"] == "Size"]
        if size_opt:
            res = _gql(token, OPTIONS_DELETE, {"productId": pid, "options": size_opt}, "productOptionsDelete")
            if res["product"]["variants"]["nodes"][0]["id"] != before["variant_id"]:
                raise RelistError(f"restore {e['supabase_id']}: original variant missing")
        _gql(token, VARIANTS_UPDATE, {"productId": pid, "variants": [{
            "id": before["variant_id"], "price": before["price"], "compareAtPrice": before["compare_at"],
            "inventoryItem": {"sku": before["sku"]}}]}, "productVariantsBulkUpdate")
        cur = ss.shopify_graphql(token, READ_QUERY, {"ids": [pid]})["nodes"][0]["variants"]["nodes"][0]
        lvl = cur["inventoryItem"]["inventoryLevel"]
        now = lvl["quantities"][0]["quantity"] if lvl else None
        if before["available"] is not None and now != before["available"]:
            ss.set_size_quantities(token, [(before["inventory_item_id"], now or 0, before["available"])],
                                   f"gid://luxella-scrapper/Relist/restore/{e['supabase_id']}")
        sb.table("products").update({"last_synced_variant_stock": None}).eq("id", e["supabase_id"]).execute()
        ok += 1
        time.sleep(0.5)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm", action="store_true", help="asli likho (default dry run)")
    ap.add_argument("--limit", type=int, default=0, help="sirf itne products")
    ap.add_argument("--only-id", type=int, help="sirf ye Supabase product id (jaise 3860 ALO Runner)")
    ap.add_argument("--restore", help="backup jsonl se wapas (with --confirm)")
    ap.add_argument("--max-age-days", type=float, default=rv.MAX_AGE_DAYS)
    args = ap.parse_args()

    sb, token = ss.get_supabase(), ss.get_access_token()
    if args.restore:
        if not args.confirm:
            n = sum(1 for line in open(args.restore) if line.strip())
            print(f"DRY RUN: {n} products wapas 'Default Title' pe jaate. --confirm se chalao.")
            return
        print(f"restored {restore(sb, token, args.restore)} products")
        return

    rows, stale = rv.split_fresh(rv.fetch_candidates(sb), args.max_age_days)
    if args.only_id:
        rows = [r for r in rows if r["id"] == args.only_id]
    print(f"{len(rows)} fresh multi-size candidates (signature null); {len(stale)} stale chhode")
    items, totals = plan(token, rows)
    totals["skipped_stale"] = len(stale)
    samples = [{"id": it["row"]["id"], "site": it["row"]["site"], "name": it["row"]["name"],
                "shopify_now": {"qty": it["shop"]["available"], "price": it["shop"]["price"]},
                "sizes": [(x["size"], x["price"], x["qty"]) for x in it["targets"]]} for it in items[:20]]
    json.dump({"totals": totals, "by_site": Counter(it["row"]["site"] for it in items).most_common(),
               "samples": samples}, open(REPORT, "w"), indent=1)
    print(json.dumps(totals, indent=1))
    for s in samples:
        print(f"  {s['site']:14} {s['name'][:38]:38} now qty={s['shopify_now']['qty']} -> "
              + ", ".join(f"{z}:{q}" for z, _, q in s["sizes"][:8]))
    if not args.confirm:
        print(f"DRY RUN - kuch nahi likha. report: {REPORT}")
        return
    done = apply(sb, token, items, args.limit)
    print(f"APPLIED: {done} products relisted; backup: {BACKUP}")


if __name__ == "__main__":
    main()
