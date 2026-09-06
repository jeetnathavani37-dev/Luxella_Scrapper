"""
remove_kicksmachine.py

One-time cleanup - kicksmachine Jeet ka apna B2B sourcing partner
platform hai, galti se competitor-scrape source ki tarah add ho gaya
tha. Ye script uska poora data hata deta hai:
1. Jo bhi kicksmachine products Shopify pe live hain, unhe DELETE
   karta hai (Shopify API se)
2. Supabase se saari kicksmachine rows delete karta hai (chahe
   pushed the ya nahi)

Requires GitHub Secrets:
    SHOPIFY_STORE_DOMAIN, SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET,
    SUPABASE_URL, SUPABASE_SERVICE_KEY

Usage:
    BATCH_SIZE=1000 python remove_kicksmachine.py
"""
import os
import time
import requests
from supabase import create_client

BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "1000"))
RATE_LIMIT_DELAY = 0.6
API_VERSION = "2025-01"


def get_supabase():
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)


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


def get_shopify_base_url():
    return f"https://{get_shopify_domain()}/admin/api/{API_VERSION}"


def delete_shopify_product(access_token, product_id):
    headers = {"X-Shopify-Access-Token": access_token}
    resp = requests.delete(f"{get_shopify_base_url()}/products/{product_id}.json", headers=headers, timeout=30)
    if resp.status_code == 404:
        return  # already deleted / never existed - fine
    resp.raise_for_status()


def run():
    sb = get_supabase()

    resp = (
        sb.table("products")
        .select("id,shopify_product_id,pushed_to_shopify")
        .eq("site", "kicksmachine")
        .not_.is_("shopify_product_id", "null")
        .limit(BATCH_SIZE)
        .execute()
    )
    to_delete_from_shopify = resp.data

    print(f"{len(to_delete_from_shopify)} products Shopify se delete karne hain is batch mein...")

    if to_delete_from_shopify:
        access_token = get_access_token()
        deleted = 0
        errors = 0
        for p in to_delete_from_shopify:
            try:
                delete_shopify_product(access_token, p["shopify_product_id"])
                sb.table("products").delete().eq("id", p["id"]).execute()
                deleted += 1
            except Exception as e:
                errors += 1
                print(f"  [ERROR] product id {p['id']} (shopify {p['shopify_product_id']}): {e}")
            time.sleep(RATE_LIMIT_DELAY)
        print(f"Shopify se deleted: {deleted}, errors: {errors}")

    # Baaki (jo kabhi push hi nahi hui thi) Supabase se seedha delete
    del_resp = sb.table("products").delete().eq("site", "kicksmachine").execute()
    remaining_deleted = len(del_resp.data) if del_resp.data else 0
    print(f"Baaki (never-pushed) rows Supabase se deleted: {remaining_deleted}")

    # Kitna bacha hai check karo
    check = sb.table("products").select("id", count="exact").eq("site", "kicksmachine").execute()
    print(f"\nKicksmachine rows ab bhi bachi hain: {check.count}")


if __name__ == "__main__":
    run()
