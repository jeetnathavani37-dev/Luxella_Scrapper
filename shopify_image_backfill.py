"""
shopify_image_backfill.py

Un products ke liye extra gallery images add karta hai jo PEHLE (multi-
image fix se pehle) push ho chuke the sirf 1 image ke saath. Naye
products (shopify_push.py se) already poori gallery ke saath aate hain
- iski zaroorat nahi. Ye sirf purane already-pushed products ke liye
one-time backfill hai.

Prerequisite: image_urls column populate honi chahiye Supabase mein
(shopify_scraper.py re-scrape karega Shopify-based brands, purane rows
update ho jaayenge) - agar image_urls null hai, ye script us product
ko skip kar dega.

Requires GitHub Secrets:
    SHOPIFY_STORE_DOMAIN, SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET

Behavior:
- 'pushed_to_shopify = true' products leta hai jinke paas image_urls
  hai (2+ images, matlab gallery available hai)
- Har product ke Shopify se current images count check karta hai
- Agar Supabase mein zyada images hain current Shopify count se, baaki
  images POST /products/{id}/images.json se add karta hai
- Tracking: 'images_backfilled' column use karta hai duplicate-processing
  avoid karne ke liye
- BATCH_SIZE se control - default 200

Usage:
    BATCH_SIZE=200 python shopify_image_backfill.py
"""
import os
import time
import requests
from supabase import create_client

BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "200"))
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


def fetch_candidates(sb, limit):
    """Pushed products jinke paas gallery (2+ images) hai aur abhi tak
    backfill nahi hua."""
    resp = (
        sb.table("products")
        .select("id,name,shopify_product_id,image_urls,images_backfilled")
        .eq("pushed_to_shopify", True)
        .not_.is_("shopify_product_id", "null")
        .not_.is_("image_urls", "null")
        .is_("images_backfilled", "null")
        .limit(limit)
        .execute()
    )
    # sirf wahi jinke paas actually 2+ images hain
    return [p for p in resp.data if isinstance(p.get("image_urls"), list) and len(p["image_urls"]) > 1]


def get_current_image_count(access_token, shopify_product_id):
    headers = {"X-Shopify-Access-Token": access_token}
    resp = requests.get(
        f"{get_shopify_base_url()}/products/{shopify_product_id}/images.json",
        headers=headers, timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("images", [])


def add_image(access_token, shopify_product_id, image_url):
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json",
    }
    payload = {"image": {"src": image_url}}
    resp = requests.post(
        f"{get_shopify_base_url()}/products/{shopify_product_id}/images.json",
        headers=headers, json=payload, timeout=30,
    )
    resp.raise_for_status()


def mark_backfilled(sb, product_id):
    sb.table("products").update({"images_backfilled": True}).eq("id", product_id).execute()


def run():
    sb = get_supabase()
    candidates = fetch_candidates(sb, BATCH_SIZE)

    if not candidates:
        print("Koi products nahi mile backfill ke liye (ya image_urls abhi populate nahi hui).")
        return

    print("Access token generate kar rahe hain...")
    access_token = get_access_token()
    print(f"Token mil gaya. {len(candidates)} products check kar rahe hain...")

    summary = {"images_added": 0, "products_processed": 0, "errors": 0}

    for p in candidates:
        try:
            shopify_id = p["shopify_product_id"]
            all_urls = p["image_urls"]

            existing_images = get_current_image_count(access_token, shopify_id)
            existing_srcs = {img["src"].split("?")[0] for img in existing_images}

            added = 0
            for url in all_urls:
                base_url = url.split("?")[0]
                if base_url in existing_srcs:
                    continue
                add_image(access_token, shopify_id, url)
                added += 1
                summary["images_added"] += 1
                time.sleep(RATE_LIMIT_DELAY)

            mark_backfilled(sb, p["id"])
            summary["products_processed"] += 1
            print(f"  [OK] {p.get('name')}: +{added} images (Shopify ID {shopify_id})")

        except Exception as e:
            summary["errors"] += 1
            print(f"  [ERROR] {p.get('name')}: {e}")

        time.sleep(RATE_LIMIT_DELAY)

    print("\n=== Summary ===")
    print(summary)


if __name__ == "__main__":
    run()
