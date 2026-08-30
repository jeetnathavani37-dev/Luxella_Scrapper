"""
shopify_publish.py

Already-pushed products ko LIVE + PUBLISHED karta hai - status ko
'draft' se 'active' AUR product ko Online Store channel pe publish
karta hai. shopify_push.py ab naye products directly active+published
banata hai, ye script sirf PURANE products ke liye hai (jo is fix se
pehle push hue the).

NOTE (2026-08-30): Do bugs fix kiye is round mein:
1. .neq("shopify_status", "active") SQL NULL-trap mein fasa tha (purane
   products ka shopify_status column NULL tha, neq() unhe skip kar deta
   hai) - fix: OR filter (neq ya is null).
2. BADA discovery: status="active" karna kaafi nahi hai - Shopify mein
   "active" status aur "Online Store channel pe published" hona DO ALAG
   cheezein hain. status=active kiya to bhi product invisible raha
   storefront pe jab tak "published": true bhi na bheja jaaye. Isliye
   is script mein ab dono set karte hain - status aur published.

Requires GitHub Secrets:
    SHOPIFY_STORE_DOMAIN, SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET

Behavior:
- 'pushed_to_shopify = true' AND (shopify_status != 'active' YA NULL)
  wale products ko batch mein leta hai
- Har ek ko Shopify pe PUT call se status='active' + published=true
  set karta hai (ek hi request mein)
- Supabase mein shopify_status='active' update karta hai
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
    """shopify_status != 'active' YA NULL - dono cases cover karta hai."""
    resp = (
        sb.table("products")
        .select("id,name,shopify_product_id,shopify_status")
        .eq("pushed_to_shopify", True)
        .not_.is_("shopify_product_id", "null")
        .or_("shopify_status.neq.active,shopify_status.is.null")
        .limit(limit)
        .execute()
    )
    return resp.data


def publish_product(access_token, shopify_product_id):
    """Status active AND Online Store publish - dono ek hi call mein."""
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json",
    }
    payload = {"product": {"id": int(shopify_product_id), "status": "active", "published": True}}
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
        print("Koi draft products nahi mile - sab already active+published hain.")
        return

    print("Access token generate kar rahe hain...")
    access_token = get_access_token()
    print("Token mil gaya.")

    print(f"{len(drafts)} products ko LIVE + PUBLISHED kar rahe hain...")

    summary = {"published": 0, "errors": 0}

    for p in drafts:
        try:
            publish_product(access_token, p["shopify_product_id"])
            mark_published(sb, p["id"])
            summary["published"] += 1
            print(f"  [LIVE+PUBLISHED] {p.get('name')} -> Shopify ID {p['shopify_product_id']}")
        except Exception as e:
            summary["errors"] += 1
            print(f"  [ERROR] {p.get('name')}: {e}")

        time.sleep(RATE_LIMIT_DELAY)

    print("\n=== Summary ===")
    print(summary)


if __name__ == "__main__":
    run()
