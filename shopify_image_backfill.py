"""
shopify_image_backfill.py

Un products ke liye extra gallery images add karta hai jo PEHLE (multi-
image fix se pehle) push ho chuke the sirf 1 image ke saath.

NOTE (2026-08-31): Fix - pehle DB se ek hi batch fetch karte the (jaise
300), phir uसमें se sirf 2+-image wale filter karte the - agar batch
mein zyada single-image products the, actual kaam kam hota (jaise
300 mangke sirf 125 process hue). Ab jab tak target count na mile ya
saare products scan na ho jaayein, agli pages fetch karta rehta hai.
Saath hi jin products ke paas sirf 1 image hai (kuch add karne ko nahi
hai), unko bhi turant 'images_backfilled=true' mark kar dete hain -
taaki wo baar baar dobara scan na ho.

NOTE (2026-09-02): run() ab kitne products actually process hue wo
count return karta hai (0 nahi) - taaki auto_pilot.py (jo push+sync+
image-backfill ko continuous loop mein chalata hai jab tak sab kuch
complete na ho jaaye) pata laga sake ki backfill mein abhi bhi kaam
bacha hai ya nahi.

Requires GitHub Secrets:
    SHOPIFY_STORE_DOMAIN, SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET

Usage:
    BATCH_SIZE=300 python shopify_image_backfill.py
"""
import os
import time
import requests
from supabase import create_client

BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "200"))
RATE_LIMIT_DELAY = 0.6
API_VERSION = "2025-01"
PAGE_SIZE = 500
MAX_PAGES = 20  # safety cap - max 10,000 rows scan karega ek run mein


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


def fetch_one_page(sb, offset):
    resp = (
        sb.table("products")
        .select("id,name,shopify_product_id,image_urls,images_backfilled")
        .eq("pushed_to_shopify", True)
        .not_.is_("shopify_product_id", "null")
        .not_.is_("image_urls", "null")
        .is_("images_backfilled", "null")
        .range(offset, offset + PAGE_SIZE - 1)
        .execute()
    )
    return resp.data


def mark_no_gallery(sb, product_id):
    """Sirf 1 image hai - kuch add karne ko nahi, isliye 'done' mark kar
    dete hain taaki dobara scan na ho."""
    sb.table("products").update({"images_backfilled": True}).eq("id", product_id).execute()


def fetch_candidates(sb, target_count):
    """Jab tak target_count real candidates (2+ images) na mil jaayein
    ya saare rows scan na ho jaayein, pages fetch karta rehta hai. Single-
    image products ko turant 'backfilled' mark kar deta hai (skip future)."""
    candidates = []
    offset = 0

    for _ in range(MAX_PAGES):
        page = fetch_one_page(sb, offset)
        if not page:
            break

        for p in page:
            urls = p.get("image_urls")
            if isinstance(urls, list) and len(urls) > 1:
                candidates.append(p)
            else:
                mark_no_gallery(sb, p["id"])

        offset += PAGE_SIZE

        if len(candidates) >= target_count:
            break

    return candidates[:target_count]


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
        return 0

    print("Access token generate kar rahe hain...")
    access_token = get_access_token()
    print(f"Token mil gaya. {len(candidates)} products (real gallery wale) backfill kar rahe hain...")

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
    return summary["products_processed"]


if __name__ == "__main__":
    run()
