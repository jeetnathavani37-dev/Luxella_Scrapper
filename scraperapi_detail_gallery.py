"""
scraperapi_detail_gallery.py

MK/Coach jaise ScraperAPI-based brands ke liye - category-listing page
se sirf 1 thumbnail milta hai, poori gallery (multiple angles) lene ke
liye har product ka INDIVIDUAL detail page visit karna padta hai. Ye
script wahi karta hai - existing products (jinke paas already 1 image
hai Supabase mein) ke product_url pe jaake poori gallery extract karta
hai, image_urls array update karta hai.

Approach: CSS selectors guess karne ki jagah (jo fragile hote hain,
site-redesign pe toot jaate hain), har site ke image-CDN URL pattern
se regex-match karta hai - zyada robust hai:
  - Michael Kors: assets.michaelkors.com/transform/ECOM_Image_Large/...
  - Coach: coach.scene7.com/is/image/Coach/...

Requires GitHub Secrets: SCRAPERAPI_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY
(sab already existing hain, koi naya secret nahi chahiye)

Behavior:
- 'site' MK/Coach wale products leta hai jinke paas image_urls
  missing/single hai, product_url available hai
- Har product ka detail page ScraperAPI se fetch karta hai (render=true)
- Site-specific regex se saari gallery image URLs nikalta hai (max 8)
- image_urls Supabase mein update karta hai - iske baad
  shopify_image_backfill.py (already automatic) inhe Shopify pe bhi
  add kar dega agla scheduled run mein

Usage:
    BATCH_SIZE=100 python scraperapi_detail_gallery.py
"""
import os
import re
import time
import requests
from supabase import create_client

BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "100"))
RATE_LIMIT_DELAY = 1.0
MAX_IMAGES_PER_PRODUCT = 8
SCRAPERAPI_URL = "https://api.scraperapi.com/"

# Site-specific image-CDN patterns - detail page HTML mein jo bhi URL
# is pattern se match kare, wo gallery image maani jaati hai.
GALLERY_PATTERNS = {
    "michaelkors": re.compile(
        r"https://assets\.michaelkors\.com/transform/ECOM_Image_Large/[^\s\"'<>]+"
    ),
    "coach": re.compile(
        r"https://coach\.scene7\.com/is/image/Coach/[^\s\"'<>]+?(?=\?|\"|'|\s)"
    ),
}


def get_supabase():
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)


def fetch_html(url, render=True, timeout=90):
    api_key = os.environ.get("SCRAPERAPI_KEY")
    if not api_key:
        raise RuntimeError("SCRAPERAPI_KEY secret set nahi hai")
    params = {
        "api_key": api_key,
        "url": url,
        "render": "true" if render else "false",
        "country_code": "us",
    }
    resp = requests.get(SCRAPERAPI_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def fetch_candidates(sb, site, limit):
    resp = (
        sb.table("products")
        .select("id,name,product_url,image_urls")
        .eq("site", site)
        .not_.is_("product_url", "null")
        .limit(limit * 2)  # extra fetch karo kyunki kuch filter honge
        .execute()
    )
    # sirf wahi jinke paas image_urls missing ya sirf 1 hai
    candidates = [
        p for p in resp.data
        if not p.get("image_urls") or (isinstance(p["image_urls"], list) and len(p["image_urls"]) <= 1)
    ]
    return candidates[:limit]


def extract_gallery(html, site):
    pattern = GALLERY_PATTERNS[site]
    matches = pattern.findall(html)
    # dedupe, order preserve karte hue
    seen = set()
    unique = []
    for url in matches:
        base = url.split("?")[0]
        if base not in seen:
            seen.add(base)
            unique.append(url)
        if len(unique) >= MAX_IMAGES_PER_PRODUCT:
            break
    return unique


def update_gallery(sb, product_id, image_urls):
    sb.table("products").update({
        "image_urls": image_urls,
        "image_url": image_urls[0] if image_urls else None,
    }).eq("id", product_id).execute()


def run():
    sb = get_supabase()
    summary = {"updated": 0, "no_images_found": 0, "errors": 0}

    for site in ("michaelkors", "coach"):
        candidates = fetch_candidates(sb, site, BATCH_SIZE)
        print(f"\n=== {site}: {len(candidates)} products (gallery missing) ===")

        for p in candidates:
            try:
                html = fetch_html(p["product_url"])
                gallery = extract_gallery(html, site)

                if gallery:
                    update_gallery(sb, p["id"], gallery)
                    summary["updated"] += 1
                    print(f"  [OK] {p.get('name')}: {len(gallery)} images")
                else:
                    summary["no_images_found"] += 1
                    print(f"  [SKIP] {p.get('name')}: koi gallery image nahi mili")

            except Exception as e:
                summary["errors"] += 1
                print(f"  [ERROR] {p.get('name')}: {e}")

            time.sleep(RATE_LIMIT_DELAY)

    print("\n=== Summary ===")
    print(summary)


if __name__ == "__main__":
    run()
