"""
shopify_push.py

Supabase 'products' table se new products ko Shopify (Luxella store) mein
push karta hai - Shopify Admin API (REST) ke through, direct API calls
(CSV import nahi - isliye ye fully automated/scheduled chal sakta hai,
manual browser upload ki zaroorat nahi).

NOTE (2026-08-30): Shopify ne 1 Jan 2026 se purana "reveal token once"
custom-app flow retire kar diya. Ab Dev Dashboard se app banti hai,
jisse sirf Client ID + Client Secret milte hain (koi static token nahi).
Actual API access token in credentials se "client credentials grant"
ke through generate hota hai - aur wo token sirf 24 ghante valid rehta
hai. Isliye ye script har run mein fresh token khud generate karta hai
(cache nahi karta - GitHub Actions runs already short-lived hain).

Requires GitHub Secrets:
    SHOPIFY_STORE_DOMAIN     = luxella-9299.myshopify.com
    SHOPIFY_CLIENT_ID        = Dev Dashboard app ka Client ID
    SHOPIFY_CLIENT_SECRET    = Dev Dashboard app ka Client secret

    (App banane ka process: dev.shopify.com/dashboard > Create app >
    Admin API scopes: write_products, read_products > Install app on
    store > API credentials tab se Client ID/Secret copy karo)

Behavior:
- Sabse pehle client_id + client_secret se ek fresh access token leta
  hai (client credentials grant - POST /admin/oauth/access_token)
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
API_VERSION = "2025-01"


def slugify(text, maxlen=60):
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return s[:maxlen]


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
    """Client credentials grant - Client ID + Secret se fresh access
    token generate karta hai (24h valid, isliye har run mein naya
    leta hai instead of storing/caching)."""
    client_id = os.environ.get("SHOPIFY_CLIENT_ID")
    client_secret = os.environ.get("SHOPIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError("SHOPIFY_CLIENT_ID / SHOPIFY_CLIENT_SECRET secrets set nahi hain")

    domain = get_shopify_domain()
    url = f"https://{domain}/admin/oauth/access_token"
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
    }
    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    token = resp.json().get("access_token")
    if not token:
        raise RuntimeError(f"Access token response mein nahi mila: {resp.json()}")
    return token


def get_shopify_base_url():
    domain = get_shopify_domain()
    return f"https://{domain}/admin/api/{API_VERSION}"


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


def create_shopify_product(payload, access_token):
    base_url = get_shopify_base_url()
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json",
    }
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

    print("Access token generate kar rahe hain (client credentials grant)...")
    access_token = get_access_token()
    print("Token mil gaya.")

    print(f"{len(pending)} products push kar rahe hain Shopify pe...")

    summary = {"pushed": 0, "errors": 0}

    for p in pending:
        try:
            payload = build_shopify_payload(p)
            shopify_product = create_shopify_product(payload, access_token)
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
