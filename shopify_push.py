"""
shopify_push.py

Supabase 'products' table se new products ko Shopify (Luxella store) mein
push karta hai - Shopify Admin API (REST) ke through, direct API calls
(CSV import nahi - isliye ye fully automated/scheduled chal sakta hai,
manual browser upload ki zaroorat nahi).

Requires GitHub Secrets:
    SHOPIFY_STORE_DOMAIN     = luxella-9299.myshopify.com
    SHOPIFY_ADMIN_API_TOKEN  = Custom app ka Admin API access token
                                (Settings > Apps > Develop apps > create
                                app > Admin API scopes: write_products,
                                read_products > Install > reveal token)

Behavior:
- 'pushed_to_shopify = false' wale products (jinke paas valid name +
  selling_price_inr hai) ko batch mein push karta hai
- Har product 'draft' status mein banta hai (safety - live nahi hota
  jab tak manually Active na kiya jaaye Shopify admin se)
- Successfully push hone pe: pushed_to_shopify=true, shopify_product_id
  aur shopify_pushed_at update karta hai - taaki agli baar duplicate na
  bane
- Shopify REST Admin API rate limit ~2 req/sec hai - isliye har call ke
  beech chhota delay hai
- BATCH_SIZE env var se control hota hai kitne products ek run mein
  push honge (default 200) - taaki GitHub Actions timeout na ho.
  16K jaisa bada backlog kai runs mein gradually clear ho jaayega agar
  ye script schedule pe chalta rahe.

Usage:
    BATCH_SIZE=200 python shopify_push.py
"""
import os
import re
import time
import requests
from datetime import datetime, timezone
from supabase import create_client

BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "200"))
RATE_LIMIT_DELAY = 0.6  # seconds between calls, ~1.6 req/sec (Shopify allows ~2/sec)


def slugify(text, maxlen=60):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return s[:maxlen]


def get_supabase():
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)


def get_shopify_headers():
    token = os.environ.get("SHOPIFY_ADMIN_API_TOKEN")
    if not token:
        raise RuntimeError("SHOPIFY_ADMIN_API_TOKEN secret set nahi hai")
    return {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
    }


def get_shopify_base_url():
    domain = os.environ.get("SHOPIFY_STORE_DOMAIN")
    if not domain:
        raise RuntimeError("SHOPIFY_STORE_DOMAIN secret set nahi hai")
    return f"https://{domain}/admin/api/2025-01"


def fetch_pending_products(sb, limit):
    """Un products ko fetch karta hai jo abhi tak Shopify pe push nahi
    hue - valid name aur selling_price honi chahiye."""
    resp = (
        sb.table("products")
        .select("id,sku,name,brand,category,selling_price_inr,image_url,in_stock,site")
        .eq("pushed_to_shopify", False)
        .not_.is_("selling_price_inr", "null")
        .not_.is_("name", "null")
        .neq("name", "")
        .limit(limit)
        .execute()
    )
    return resp.data


def build_shopify_payload(p):
    """Supabase row ko Shopify product-create payload mein convert karta hai."""
    name = (p.get("name") or "").strip()
    brand = (p.get("brand") or p.get("site") or "luxella").strip()
    sku = (p.get("sku") or "").strip() or f"LX-{p['id']}"
    price = str(p.get("selling_price_inr") or "0")
    category = (p.get("category") or "uncategorized").strip()
    image_url = p.get("image_url")
    in_stock = bool(p.get("in_stock"))

    title = f"{brand.title()} {name}".strip()[:255]

    payload = {
        "product": {
            "title": title,
            "body_html": f"<p>{title}</p><p>Sourced via Luxella.</p>",
            "vendor": brand.title(),
            "product_type": category.title(),
            "tags": f"{brand}, {category}",
            "status": "draft",
            "variants": [
                {
                    "sku": sku,
                    "price": price,
                    "inventory_management": "shopify",
                    "inventory_policy": "deny",
                    "inventory_quantity": 10 if in_stock else 0,
                }
            ],
        }
    }
    if image_url:
        payload["product"]["images"] = [{"src": image_url}]

    return payload


def create_shopify_product(payload):
    base_url = get_shopify_base_url()
    headers = get_shopify_headers()
    resp = requests.post(f"{base_url}/products.json", headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()["product"]


def mark_pushed(sb, product_id, shopify_product_id):
    sb.table("products").update({
        "pushed_to_shopify": True,
        "shopify_product_id": str(shopify_product_id),
        "shopify_pushed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", product_id).execute()


def run():
    sb = get_supabase()
    pending = fetch_pending_products(sb, BATCH_SIZE)

    if not pending:
        print("Koi pending products nahi hain push karne ke liye.")
        return

    print(f"{len(pending)} products push kar rahe hain Shopify pe...")

    summary = {"pushed": 0, "errors": 0}

    for p in pending:
        try:
            payload = build_shopify_payload(p)
            shopify_product = create_shopify_product(payload)
            mark_pushed(sb, p["id"], shopify_product["id"])
            summary["pushed"] += 1
            print(f"  [OK] {p.get('name')} -> Shopify ID {shopify_product['id']}")
        except Exception as e:
            summary["errors"] += 1
            print(f"  [ERROR] {p.get('name')}: {e}")

        time.sleep(RATE_LIMIT_DELAY)

    print("\n=== Summary ===")
    print(summary)


if __name__ == "__main__":
    run()
