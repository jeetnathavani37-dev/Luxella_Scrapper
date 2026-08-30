"""
shopify_backfill_ids.py

One-time repair script - un products ke liye jo pushed_to_shopify=true
hain lekin shopify_variant_id/shopify_inventory_item_id Supabase mein
NULL hai (kyunki wo variant-tracking feature add hone SE PEHLE push
hue the - shuru ke 1731 products isi category mein hain).

Har product ka shopify_product_id already pata hai - isse Shopify se
GET karke variant/inventory IDs wapas nikaal ke Supabase update karta
hai. Isके baad shopify_sync.py in products ko bhi properly sync kar
paayega (price/stock/MRP).

Requires GitHub Secrets:
    SHOPIFY_STORE_DOMAIN, SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET

Usage:
    BATCH_SIZE=300 python shopify_backfill_ids.py
"""
import os
import time
import requests
from supabase import create_client

BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "300"))
RATE_LIMIT_DELAY = 0.6
API_VERSION = "2025-01"


def get_supabase():
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)


def get_shopify_domain():
    domain = os.environ.get("SHOPIFY_STORE_DOMAIN")
    if not domain:
        raise RuntimeError("SHOPIFY_STORE_DOMAIN secret set nahi hai")
    return domain


def get_access_token():
    client_id = os.environ.get("SHOPIFY_CLIENT_ID")
    client_secret = os.environ.get("SHOPIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("SHOPIFY_CLIENT_ID / SHOPIFY_CLIENT_SECRET secrets set nahi hain")

    resp = requests.post(
        f"https://{get_shopify_domain()}/admin/oauth/access_token",
        json={"client_id": client_id, "client_secret": client_secret, "grant_type": "client_credentials"},
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.json().get("access_token")
    if not token:
        raise RuntimeError(f"Access token response mein nahi mila: {resp.json()}")
    return token


def get_shopify_base_url():
    return f"https://{get_shopify_domain()}/admin/api/{API_VERSION}"


def fetch_missing_id_products(sb, limit):
    resp = (
        sb.table("products")
        .select("id,name,shopify_product_id")
        .eq("pushed_to_shopify", True)
        .not_.is_("shopify_product_id", "null")
        .is_("shopify_variant_id", "null")
        .limit(limit)
        .execute()
    )
    return resp.data


def get_shopify_product(access_token, shopify_product_id):
    headers = {"X-Shopify-Access-Token": access_token}
    resp = requests.get(
        f"{get_shopify_base_url()}/products/{shopify_product_id}.json",
        headers=headers, timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["product"]


def backfill_ids(sb, product_id, variant):
    sb.table("products").update({
        "shopify_variant_id": str(variant["id"]),
        "shopify_inventory_item_id": str(variant["inventory_item_id"]),
        "last_synced_price_inr": variant["price"],
    }).eq("id", product_id).execute()


def run():
    sb = get_supabase()
    candidates = fetch_missing_id_products(sb, BATCH_SIZE)

    if not candidates:
        print("Koi products nahi mile backfill ke liye - sab already IDs ke saath hain.")
        return

    print("Access token generate kar rahe hain...")
    access_token = get_access_token()
    print(f"Token mil gaya. {len(candidates)} products backfill kar rahe hain...")

    summary = {"backfilled": 0, "errors": 0}

    for p in candidates:
        try:
            shopify_product = get_shopify_product(access_token, p["shopify_product_id"])
            variant = shopify_product["variants"][0]
            backfill_ids(sb, p["id"], variant)
            summary["backfilled"] += 1
            print(f"  [OK] {p.get('name')} -> variant {variant['id']}, inventory_item {variant['inventory_item_id']}")
        except Exception as e:
            summary["errors"] += 1
            print(f"  [ERROR] {p.get('name')}: {e}")

        time.sleep(RATE_LIMIT_DELAY)

    print("\n=== Summary ===")
    print(summary)


if __name__ == "__main__":
    run()
