"""
dedupe_products.py

Existing catalog mein duplicates dhoondhta hai (jaise same Coach bag
alag-alag sites pe alag price pe) - sabse SASTA wala rakhta hai, baaki
sabko Shopify se DELETE karta hai aur Supabase mein "is_duplicate"
mark kar deta hai (row delete nahi karte, taaki history/reference
rahe - bas Shopify se hata dete hain aur future push/sync se exclude
kar dete hain).

Requires GitHub Secrets:
    SUPABASE_URL, SUPABASE_SERVICE_KEY, SHOPIFY_STORE_DOMAIN,
    SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET

Usage:
    BATCH_SIZE=5000 python dedupe_products.py
"""
import os
import time
from collections import defaultdict

import requests
from supabase import create_client

from dedup_utils import compute_fingerprint

BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "5000"))
RATE_LIMIT_DELAY = 0.5
API_VERSION = "2025-01"


def get_supabase():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def get_shopify_domain():
    return os.environ["SHOPIFY_STORE_DOMAIN"]


def get_access_token():
    client_id = os.environ["SHOPIFY_CLIENT_ID"]
    client_secret = os.environ["SHOPIFY_CLIENT_SECRET"]
    resp = requests.post(
        f"https://{get_shopify_domain()}/admin/oauth/access_token",
        json={"client_id": client_id, "client_secret": client_secret, "grant_type": "client_credentials"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def delete_shopify_product(access_token, product_id):
    headers = {"X-Shopify-Access-Token": access_token}
    resp = requests.delete(
        f"https://{get_shopify_domain()}/admin/api/{API_VERSION}/products/{product_id}.json",
        headers=headers, timeout=30,
    )
    if resp.status_code == 404:
        return
    resp.raise_for_status()


def run():
    sb = get_supabase()

    print("Products fetch kar rahe hain fingerprint compute karne ke liye...")
    resp = (
        sb.table("products")
        .select("id,name,brand,selling_price_inr,shopify_product_id,pushed_to_shopify,is_duplicate")
        .eq("pushed_to_shopify", True)
        .is_("is_duplicate", "null")
        .limit(BATCH_SIZE)
        .execute()
    )
    products = resp.data
    print(f"{len(products)} pushed products mile.")

    groups = defaultdict(list)
    for p in products:
        fp = compute_fingerprint(p.get("brand"), p.get("name"))
        if fp:
            groups[fp].append(p)

    duplicate_groups = {fp: items for fp, items in groups.items() if len(items) > 1}
    print(f"{len(duplicate_groups)} duplicate-groups mile (2+ products same fingerprint pe).")

    if not duplicate_groups:
        print("Koi duplicates nahi mile.")
        return

    access_token = get_access_token()
    total_removed = 0
    total_kept = 0

    for fp, items in duplicate_groups.items():
        items_with_price = [i for i in items if i.get("selling_price_inr") is not None]
        if len(items_with_price) < 2:
            continue

        items_sorted = sorted(items_with_price, key=lambda i: i["selling_price_inr"])
        cheapest = items_sorted[0]
        to_remove = items_sorted[1:]

        print(f"\n[{fp[:60]}] KEEP: {cheapest['name']} @ Rs{cheapest['selling_price_inr']}")
        total_kept += 1

        for item in to_remove:
            try:
                # Update fingerprint on cheapest too (for future runs' reference)
                sb.table("products").update({"product_fingerprint": fp}).eq("id", cheapest["id"]).execute()

                if item.get("shopify_product_id"):
                    delete_shopify_product(access_token, item["shopify_product_id"])
                sb.table("products").update({
                    "is_duplicate": True,
                    "product_fingerprint": fp,
                }).eq("id", item["id"]).execute()
                print(f"  REMOVED: {item['name']} @ Rs{item['selling_price_inr']}")
                total_removed += 1
                time.sleep(RATE_LIMIT_DELAY)
            except Exception as e:
                print(f"  [ERROR] removing product id {item['id']}: {e}")

    print(f"\n=== Summary ===")
    print(f"Groups with duplicates: {len(duplicate_groups)}")
    print(f"Products kept (cheapest): {total_kept}")
    print(f"Products removed (pricier duplicates): {total_removed}")


if __name__ == "__main__":
    run()
