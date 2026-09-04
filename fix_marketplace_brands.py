"""
fix_marketplace_brands.py

One-time repair script - marketplace sites (GOAT, StockX, Sephora,
Kohl's, Gilt, Rue La La, SecretSales, Zappos, Ulta) ke purane
scraped/pushed products ka "brand" field galat tha (site-name, jaise
"goat", use ho raha tha - jabki asli products Supreme/Nike/Adidas jaise
alag-alag brands ke hote hain).

Ye script:
1. Har affected product ka naam se sahi brand nikaalta hai
   (brand_extractor.py se)
2. Supabase 'brand' column update karta hai
3. Agar product already Shopify pe pushed hai, uska TITLE bhi update
   karta hai (naye sahi brand ke saath) - warna sirf Supabase change
   hoti, live listing purani galat titles dikhati rehti

Requires GitHub Secrets:
    SHOPIFY_STORE_DOMAIN, SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET,
    SUPABASE_URL, SUPABASE_SERVICE_KEY

Usage:
    BATCH_SIZE=300 python fix_marketplace_brands.py
"""
import os
import time
import requests
from supabase import create_client

from brand_extractor import extract_brand

BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "300"))
RATE_LIMIT_DELAY = 0.6
API_VERSION = "2025-01"

MARKETPLACE_SITES = [
    "goat", "stockx", "sephora", "kohls", "gilt",
    "ruelala", "secretsales", "zappos", "ultabeauty",
]


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


def fetch_candidates(sb, limit):
    resp = (
        sb.table("products")
        .select("id,name,brand,site,shopify_product_id,pushed_to_shopify")
        .in_("site", MARKETPLACE_SITES)
        .is_("brand_fixed", "null")
        .limit(limit)
        .execute()
    )
    return resp.data


def update_shopify_title(access_token, shopify_product_id, new_title, new_brand):
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json",
    }
    payload = {"product": {"id": int(shopify_product_id), "title": new_title, "vendor": new_brand}}
    resp = requests.put(
        f"{get_shopify_base_url()}/products/{shopify_product_id}.json",
        headers=headers, json=payload, timeout=30,
    )
    resp.raise_for_status()


def update_supabase(sb, product_id, new_brand):
    sb.table("products").update({
        "brand": new_brand,
        "brand_fixed": True,
    }).eq("id", product_id).execute()


def run():
    sb = get_supabase()
    candidates = fetch_candidates(sb, BATCH_SIZE)

    if not candidates:
        print("Koi products nahi mile fix karne ke liye - sab already sahi hain.")
        return 0

    print("Access token generate kar rahe hain...")
    access_token = get_access_token()
    print(f"Token mil gaya. {len(candidates)} products ka brand fix kar rahe hain...")

    summary = {"brand_fixed": 0, "shopify_title_updated": 0, "no_match_kept_old": 0, "errors": 0}

    for p in candidates:
        try:
            name = p.get("name")
            old_brand = p.get("brand")
            new_brand = extract_brand(name)

            if not new_brand:
                # Koi known brand nahi mila - purana brand hi rehne do,
                # bas 'processed' mark kar do taaki dobara scan na ho
                sb.table("products").update({"brand_fixed": True}).eq("id", p["id"]).execute()
                summary["no_match_kept_old"] += 1
                continue

            update_supabase(sb, p["id"], new_brand)
            summary["brand_fixed"] += 1
            print(f"  [BRAND] {name}: '{old_brand}' -> '{new_brand}'")

            if p.get("pushed_to_shopify") and p.get("shopify_product_id"):
                new_title = f"{new_brand} {name}".strip()[:255]
                update_shopify_title(access_token, p["shopify_product_id"], new_title, new_brand)
                summary["shopify_title_updated"] += 1
                time.sleep(RATE_LIMIT_DELAY)

        except Exception as e:
            summary["errors"] += 1
            print(f"  [ERROR] {p.get('name')}: {e}")

        time.sleep(RATE_LIMIT_DELAY)

    print("\n=== Summary ===")
    print(summary)
    return summary["brand_fixed"] + summary["no_match_kept_old"]


if __name__ == "__main__":
    run()
