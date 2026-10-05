"""
backfill_shopify_vendor.py

One-time backfill (2026-10-04): purane pushed products ka Shopify vendor/
title/tags site-slug se bana tha (shopify_push.py `brand.title()`) - jaise
vendor "Stevemadden", "Ilovedooney", "Goat" aur title "Stevemadden DIVY
LIME LEATHER". PR #13 ke baad naye products sahi naam ke saath jaate hain;
ye script PURANE products theek karta hai, brand_extractor.display_brand()
se (wahi logic jo shopify_push ab use karta hai).

Safe rules - sirf wahi badalta hai jo purane slug-pattern se bana tha:
- vendor: sirf agar abhi bhi DB brand ka .title() hai (koi manual vendor
  edit nahi chhuta) -> asli brand, ya pata na ho to "Luxella"
- title: sirf agar title "<Brand.title()> " se shuru hota hai aur woh
  prefix galat hai -> prefix asli brand se badal do (ya hata do)
- tags: raw slug tag hatao, asli brand tag jodo; baaki tags waise hi
Handle/URL nahi badalta (productUpdate me handle nahi bhejte).

Flow: Shopify bulk export (id,title,vendor,tags) + Supabase rows ->
changes plan -> DRY_RUN me sirf summary + samples; DRY_RUN=0 pe ek
Shopify bulk mutation (productUpdate) - 50k products minutes me.

Requires: SUPABASE_URL, SUPABASE_SERVICE_KEY, SHOPIFY_STORE_DOMAIN,
          SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET

Usage:
    DRY_RUN=1 python backfill_shopify_vendor.py      # default - kuch nahi badalta
    DRY_RUN=0 python backfill_shopify_vendor.py
    EXPORT_JSONL=export.jsonl DRY_RUN=1 ...           # Shopify export file pehle se ho to (offline plan)
"""
import json
import os
import time
from collections import Counter

import requests
from supabase import create_client

from brand_extractor import BRAND_DISPLAY, _marketplace_slugs, display_brand

API_VERSION = "2025-01"
DRY_RUN = os.environ.get("DRY_RUN", "1") != "0"
PAGE = 1000  # Supabase (PostgREST) ek request me max 1000 rows deta hai
UPDATE_MUTATION = (
    "mutation call($product: ProductUpdateInput!) { productUpdate(product: $product) "
    "{ product { id } userErrors { field message } } }"
)


# ---------- planning (pure) ----------

def plan_change(row, shop):
    """row: Supabase {brand,name,site}; shop: {id,title,vendor,tags}. Returns update dict or None."""
    name = (row.get("name") or "").strip()
    site = (row.get("site") or "").strip()
    brand = (row.get("brand") or site or "luxella").strip()
    shown = display_brand(brand, name)
    # Purane push ne "<X.title()>" lagaya tha - X = us waqt ka brand (aksar site slug). Baad me
    # fix_marketplace_brands ne DB brand badla par Shopify me site slug reh gaya, isliye dono dekho.
    old = {x.title() for x in (brand, site) if x} - {shown}
    slugs = {x.lower() for x in (brand, site) if x and (not shown or x.lower() != shown.lower())}
    upd = {}

    vendor = shop.get("vendor") or ""
    new_vendor = shown or "Luxella"
    if vendor in old and vendor != new_vendor:
        upd["vendor"] = new_vendor

    title = shop.get("title") or ""
    for prefix in sorted(old, key=len, reverse=True):
        if title.startswith(prefix + " "):
            rest = title[len(prefix) + 1:].strip()
            if shown and not rest.lower().startswith(shown.lower()):
                new_title = f"{shown} {rest}"
            else:
                new_title = rest
            new_title = new_title.strip()[:255]
            if new_title and new_title != title:
                upd["title"] = new_title
            break

    tags = list(shop.get("tags") or [])
    # slug tags ("stevemadden", "zappos") hatao; sirf case ka farak ho ("coach"/"Coach") to chhod do
    new_tags = [t for t in tags if t.strip().lower() not in slugs]
    if shown and shown.lower() not in {t.strip().lower() for t in new_tags}:
        new_tags.append(shown)
    if sorted(new_tags) != sorted(tags):
        upd["tags"] = new_tags

    if not upd:
        return None
    upd["id"] = shop["id"]
    return upd


# ---------- data ----------

def get_supabase():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def load_rows(sb):
    """shopify gid -> {brand,name,site} for every pushed product."""
    rows, offset = {}, 0
    while True:
        data = (sb.table("products").select("brand,name,site,shopify_product_id")
                .eq("pushed_to_shopify", True).not_.is_("shopify_product_id", "null")
                .order("id").range(offset, offset + PAGE - 1).execute().data)
        for r in data:
            rows[f"gid://shopify/Product/{r['shopify_product_id']}"] = r
        if len(data) < PAGE:
            return rows
        offset += PAGE


def get_access_token():
    resp = requests.post(
        f"https://{os.environ['SHOPIFY_STORE_DOMAIN']}/admin/oauth/access_token",
        json={"client_id": os.environ["SHOPIFY_CLIENT_ID"],
              "client_secret": os.environ["SHOPIFY_CLIENT_SECRET"],
              "grant_type": "client_credentials"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def gql(token, query, variables=None):
    resp = requests.post(
        f"https://{os.environ['SHOPIFY_STORE_DOMAIN']}/admin/api/{API_VERSION}/graphql.json",
        headers={"X-Shopify-Access-Token": token, "Content-Type": "application/json"},
        json={"query": query, "variables": variables or {}}, timeout=60,
    )
    resp.raise_for_status()
    body = resp.json()
    if body.get("errors"):
        raise RuntimeError(f"GraphQL errors: {body['errors']}")
    return body["data"]


def wait_bulk(token, op_id, label):
    while True:
        time.sleep(5)
        op = gql(token, "query($id: ID!) { node(id: $id) { ... on BulkOperation "
                        "{ status errorCode objectCount url partialDataUrl } } }", {"id": op_id})["node"]
        print(f"  [{label}] {op['status']} objects={op['objectCount']}")
        if op["status"] not in ("CREATED", "RUNNING"):
            return op


def export_products(token):
    data = gql(token, "mutation($q: String!) { bulkOperationRunQuery(query: $q) "
                      "{ bulkOperation { id } userErrors { message } } }",
               {"q": "{ products { edges { node { id title vendor tags } } } }"})["bulkOperationRunQuery"]
    if data["userErrors"]:
        raise RuntimeError(data["userErrors"])
    op = wait_bulk(token, data["bulkOperation"]["id"], "export")
    if op["status"] != "COMPLETED":
        raise RuntimeError(f"export failed: {op}")
    if not op["url"]:
        return []
    text = requests.get(op["url"], timeout=300).text
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def run_bulk_update(token, updates):
    jsonl = "\n".join(json.dumps({"product": u}, ensure_ascii=False) for u in updates) + "\n"
    staged = gql(token, """mutation { stagedUploadsCreate(input: [{ resource: BULK_MUTATION_VARIABLES,
        filename: "vendor-backfill.jsonl", mimeType: "text/jsonl", httpMethod: POST }]) {
        stagedTargets { url parameters { name value } } userErrors { message } } }""")["stagedUploadsCreate"]
    if staged["userErrors"]:
        raise RuntimeError(staged["userErrors"])
    target = staged["stagedTargets"][0]
    params = {p["name"]: p["value"] for p in target["parameters"]}
    up = requests.post(target["url"], data=params,
                       files={"file": ("vendor-backfill.jsonl", jsonl.encode(), "text/jsonl")}, timeout=300)
    up.raise_for_status()
    data = gql(token, "mutation($m: String!, $p: String!) { bulkOperationRunMutation(mutation: $m, "
                      "stagedUploadPath: $p) { bulkOperation { id } userErrors { message } } }",
               {"m": UPDATE_MUTATION, "p": params["key"]})["bulkOperationRunMutation"]
    if data["userErrors"]:
        raise RuntimeError(data["userErrors"])
    op = wait_bulk(token, data["bulkOperation"]["id"], "update")
    errors = 0
    if op.get("url"):
        for line in requests.get(op["url"], timeout=300).text.splitlines():
            if not line.strip():
                continue
            res = json.loads(line)
            ue = (((res.get("data") or {}).get("productUpdate") or {}).get("userErrors")) or []
            if ue or res.get("errors"):
                errors += 1
                if errors <= 10:
                    print("  [ERROR]", ue or res.get("errors"))
    print(f"Bulk update {op['status']} ({op.get('errorCode')}), objects={op['objectCount']}, errors={errors}")
    return op, errors


def orphan_row(shop):
    """Shopify product jiska Supabase row nahi (purani deleted rows). Sirf tab jab vendor ek
    jaana-pehchana slug ho (BRAND_DISPLAY ya marketplace) - baaki (jaise Luxlair) ko mat chhuo."""
    vendor = (shop.get("vendor") or "").strip()
    slug = vendor.lower()
    if not slug or (slug not in BRAND_DISPLAY and slug not in _marketplace_slugs()):
        return None
    title = shop.get("title") or ""
    name = title[len(vendor) + 1:] if title.startswith(vendor + " ") else title
    return {"brand": slug, "site": slug, "name": name}


def main():
    sb = get_supabase()
    rows = load_rows(sb)
    print(f"Supabase pushed rows: {len(rows)}")

    token = None
    if os.environ.get("EXPORT_JSONL"):
        products = [json.loads(line) for line in open(os.environ["EXPORT_JSONL"]) if line.strip()]
    else:
        token = get_access_token()
        products = export_products(token)
    print(f"Shopify products: {len(products)}")

    updates, fields, by_vendor, samples, unmatched = [], Counter(), Counter(), [], 0
    for shop in products:
        row = rows.get(shop["id"]) or orphan_row(shop)
        if not row:
            unmatched += 1
            continue
        upd = plan_change(row, shop)
        if not upd:
            continue
        updates.append(upd)
        fields.update(k for k in upd if k != "id")
        if "vendor" in upd:
            by_vendor[f"{shop.get('vendor')} -> {upd['vendor']}"] += 1
        if len(samples) < 12:
            samples.append((shop, upd))

    print(f"\nProducts to update: {len(updates)} (fields: {dict(fields)}); "
          f"Shopify products with no Supabase row and unknown vendor (untouched): {unmatched}")
    print("Top vendor changes:")
    for k, n in by_vendor.most_common(25):
        print(f"  {n:6d}  {k}")
    print("Samples:")
    for shop, upd in samples:
        print(f"  {shop.get('vendor')!r} / {shop.get('title')!r}\n    -> {({k: v for k, v in upd.items() if k != 'id'})}")

    if DRY_RUN:
        print("\nDRY RUN - Shopify me kuch nahi badla. Asli update ke liye DRY_RUN=0.")
        return
    if not updates:
        print("Kuch update karne ko nahi.")
        return
    token = token or get_access_token()
    op, errors = run_bulk_update(token, updates)
    if op["status"] != "COMPLETED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
