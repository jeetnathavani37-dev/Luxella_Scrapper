"""
shopify_bg_removal.py

Har pushed product ki PEHLI Shopify image ka background hata ke usko
naya PRIMARY image bana deta hai (background transparent PNG). Purani
white-bg image delete nahi hoti - gallery mein 2nd image ban jaati hai
(safe/reversible), sirf position badalta hai.

Kaam local ML model (rembg, U^2-Net - Apache 2.0 licensed, commercial
use allowed) se hota hai - koi paid API/credits nahi chahiye. Pehli
baar chalne pe rembg khud u2net.onnx model download karta hai
(~176MB, GitHub releases se) aur cache kar leta hai - agli runs fast
hongi.

Requires GitHub Secrets:
    SUPABASE_URL, SUPABASE_SERVICE_KEY, SHOPIFY_STORE_DOMAIN,
    SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET

Requires Supabase 'products' table mein do naye columns (ek baar ka
migration, SQL editor mein chalao):
    alter table products
      add column if not exists bg_removed boolean,
      add column if not exists bg_removed_at timestamptz;

Usage:
    BATCH_SIZE=50 python shopify_bg_removal.py
"""
import base64
import os
import time
from datetime import datetime, timezone

import requests
from rembg import remove
from supabase import create_client

BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "50"))
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


def fetch_pending_products(sb, limit):
    resp = (
        sb.table("products")
        .select("id,name,shopify_product_id")
        .eq("pushed_to_shopify", True)
        .not_.is_("shopify_product_id", "null")
        .is_("bg_removed", "null")
        .limit(limit)
        .execute()
    )
    return resp.data


def get_primary_image(access_token, shopify_product_id):
    headers = {"X-Shopify-Access-Token": access_token}
    resp = requests.get(
        f"{get_shopify_base_url()}/products/{shopify_product_id}/images.json",
        headers=headers, timeout=30,
    )
    resp.raise_for_status()
    images = resp.json().get("images", [])
    return images[0] if images else None


def add_cutout_as_primary(access_token, shopify_product_id, png_bytes):
    """Cutout ko position 1 pe naya image bana deta hai - Shopify khud
    baaki images ko peeche shift kar deta hai, kuch delete nahi hota."""
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json",
    }
    payload = {
        "image": {
            "attachment": base64.b64encode(png_bytes).decode("ascii"),
            "position": 1,
        }
    }
    resp = requests.post(
        f"{get_shopify_base_url()}/products/{shopify_product_id}/images.json",
        headers=headers, json=payload, timeout=60,
    )
    resp.raise_for_status()


def mark_bg_removed(sb, product_id):
    sb.table("products").update({
        "bg_removed": True,
        "bg_removed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", product_id).execute()


def run():
    sb = get_supabase()
    pending = fetch_pending_products(sb, BATCH_SIZE)

    if not pending:
        print("Koi products nahi hain background-removal ke liye pending.")
        return 0

    print("Access token generate kar rahe hain...")
    access_token = get_access_token()
    print(f"Token mil gaya. {len(pending)} products process kar rahe hain...")

    summary = {"processed": 0, "no_image": 0, "errors": 0}

    for p in pending:
        try:
            shopify_id = p["shopify_product_id"]
            image = get_primary_image(access_token, shopify_id)
            if not image:
                print(f"  [SKIP] {p.get('name')}: koi image nahi hai Shopify pe")
                mark_bg_removed(sb, p["id"])
                summary["no_image"] += 1
                continue

            original_bytes = requests.get(image["src"], timeout=30).content
            cutout_bytes = remove(original_bytes)

            add_cutout_as_primary(access_token, shopify_id, cutout_bytes)
            mark_bg_removed(sb, p["id"])
            summary["processed"] += 1
            print(f"  [OK] {p.get('name')} (Shopify ID {shopify_id})")

        except Exception as e:
            summary["errors"] += 1
            print(f"  [ERROR] {p.get('name')}: {e}")

        time.sleep(RATE_LIMIT_DELAY)

    print("\n=== Summary ===")
    print(summary)
    return summary["processed"]


if __name__ == "__main__":
    run()
