"""
shopify_publish.py

Already-pushed (jo pehle 'draft' status mein bane the) products ko
LIVE karta hai - status ko 'draft' se 'active' mein change karta hai
Shopify pe. shopify_push.py ab naye products directly 'active' banata
hai, ye script sirf PURANE draft products ke liye ek-baar (ya jab tak
sab clear na ho) chalana hai.

Requires GitHub Secrets:
    SHOPIFY_STORE_DOMAIN, SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET
    (same jaise shopify_push.py)

Behavior:
- 'pushed_to_shopify = true' AND (shopify_status != 'active' ya null)
  wale products ko batch mein leta hai
- Har ek ko Shopify pe PUT call se status='active' set karta hai
- Supabase mein shopify_status='active' update karta hai (taaki dobara
  process na ho)
- BATCH_SIZE se control - default 300

Usage:
    BATCH_SIZE=300 python shopify_publish.py
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


def fetch_draft_products(sb, limit):
    resp = (
        sb.table("products")
        .select("id,name,shopify_product_id,shopify_status")
        .eq("pushed_to_shopify", True)
        .not_.is_("shopify_product_id", "null")
        .neq("shopify_status", "active")
        .limit(limit)
        .execute()
    )
    return resp.data


def publish_product(access_token, shopify_product_id):
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json",
    }
    payload = {"product": {"id": int(shopify_product_id), "status": "active"}}
    resp = requests.put(
        f"{get_shopify_base_url()}/products/{shopify_product_id}.json",
        headers=headers, json=payload, timeout=30,
    )
    resp.raise_for_status()


def mark_published(sb, product_id):
    sb.table("products").update({"shopify_status": "active"}).eq("id", product_id).execute()


def run():
    sb = get_supabase()
    drafts = fetch_draft_products(sb, BATCH_SIZE)

    if not drafts:
        print("Koi draft products nahi mile - sab already active hain.")
        return

    print("Access token generate kar rahe hain...")
    access_token = get_access_token()
    print("Token mil gaya.")

    print(f"{len(drafts)} products ko LIVE kar rahe hain...")

    summary = {"published": 0, "errors": 0}

    for p in drafts:
        try:
            publish_product(access_token, p["shopify_product_id"])
            mark_published(sb, p["id"])
            summary["published"] += 1
            print(f"  [LIVE] {p.get('name')} -> Shopify ID {p['shopify_product_id']}")
        except Exception as e:
            summary["errors"] += 1
            print(f"  [ERROR] {p.get('name')}: {e}")

        time.sleep(RATE_LIMIT_DELAY)

    print("\n=== Summary ===")
    print(summary)


if __name__ == "__main__":
    run()
