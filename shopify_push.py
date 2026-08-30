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

NOTE (2026-08-30) #2: Discover kiya ki product-create ke time
'variants[].inventory_quantity' field Shopify silently ignore kar deta
hai - naya product hamesha 0 stock se banta hai, chahe payload mein
kuch bhi ho. Sahi stock set karne ke liye alag se
'inventory_levels/set' API call chahiye (location_id + inventory_item_id
ke saath) - CREATE ke turant baad. Ye fix kar diya hai neeche.

NOTE (2026-08-30) #3: Ab poori image gallery bhejte hain (Supabase ke
'image_urls' array se, jo shopify_scraper.py Shopify-based brands ke
liye already capture karta hai) - pehle sirf 'image_url' (1 image) bhejte
the. Non-Shopify-sourced brands (MK/Coach/StockX/GOAT jaise ScraperAPI
wale) ke paas abhi bhi sirf 1 image hai (image_urls null) - unke liye
gallery lene ke liye alag, bada scraping kaam chahiye (per-product-page
visit) - abhi sirf listing-page thumbnail milta hai.

NOTE (2026-08-30) #4: User ne decide kiya ki products ab directly LIVE
(status="active") jaayenge, draft mein nahi rukenge - pehle safety ke
liye draft rakha tha. Naye pushes se ab active status set hota hai.

NOTE (2026-08-30) #5: BADA discovery - status="active" hone ke bawajood
product Online Store par nahi dikhta jab tak wo kisi sales channel pe
"published" na ho! "status" aur "published to Online Store channel"
Shopify mein DO ALAG cheezein hain. Isliye "sirf 1 product website pe
dikh raha tha" - wahi ek product pehle se publish tha, baaki sab active
hote hue bhi published_at=null the. Fix: payload mein "published": true
add kiya - isse Shopify product ko default/Online Store channel pe bhi
publish kar deta hai (published_scope: "global").

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
- Store ki default location fetch karta hai (inventory set karne ke
  liye zaroori hai)
- 'pushed_to_shopify = false' wale products (jinke paas valid name +
  selling_price_inr hai) ko batch mein push karta hai
- Har product 'active' status + 'published: true' ke saath banta hai
  (LIVE, Online Store pe dikhega)
- Poori image gallery bhejta hai (image_urls array agar available hai,
  warna image_url fallback)
- Product create hone ke turant baad, actual stock quantity set karta
  hai (inventory_levels/set) - kyunki create-time inventory_quantity
  field Shopify ignore kar deta hai
- Successfully push hone pe: pushed_to_shopify=true, shopify_product_id,
  shopify_variant_id, shopify_inventory_item_id, shopify_status,
  last_synced_price_inr, last_synced_in_stock, shopify_synced_at - sab
  update karta hai
- Shopify REST Admin API rate limit ~2 req/sec hai - isliye har call ke
  beech chhota delay hai
- BATCH_SIZE env var se control hota hai kitne products ek run mein
  push honge (default 200)

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
    return f"https://{get_shopify_domain()}/admin/api/{API_VERSION}"


def get_default_location_id(access_token):
    """Store ki pehli/default location ka ID leta hai - inventory set
    karne ke liye zaroori hai."""
    headers = {"X-Shopify-Access-Token": access_token}
    resp = requests.get(f"{get_shopify_base_url()}/locations.json", headers=headers, timeout=30)
    resp.raise_for_status()
    locations = resp.json().get("locations", [])
    if not locations:
        raise RuntimeError("Store mein koi location nahi mili")
    return locations[0]["id"]


def fetch_pending_products(sb, limit):
    resp = (
        sb.table("products")
        .select("id,sku,name,brand,category,selling_price_inr,image_url,image_urls,in_stock,site")
        .eq("pushed_to_shopify", False)
        .not_.is_("selling_price_inr", "null")
        .not_.is_("name", "null")
        .neq("name", "")
        .limit(limit)
        .execute()
    )
    return resp.data


def get_all_image_urls(p):
    """image_urls (poori gallery) use karta hai agar available hai,
    warna single image_url pe fallback karta hai."""
    urls = p.get("image_urls")
    if urls and isinstance(urls, list) and len(urls) > 0:
        return urls
    single = p.get("image_url")
    return [single] if single else []


def build_shopify_payload(p):
    name = (p.get("name") or "").strip()
    brand = (p.get("brand") or p.get("site") or "luxella").strip()
    sku = (p.get("sku") or "").strip() or f"LX-{p['id']}"
    price = str(p.get("selling_price_inr") or "0")
    category = (p.get("category") or "uncategorized").strip()
    image_urls = get_all_image_urls(p)

    title = f"{brand.title()} {name}".strip()[:255]

    payload = {
        "product": {
            "title": title,
            "body_html": f"<p>{title}</p><p>Sourced via Luxella.</p>",
            "vendor": brand.title(),
            "product_type": category.title(),
            "tags": f"{brand}, {category}",
            "status": "active",
            "published": True,
            "variants": [
                {
                    "sku": sku,
                    "price": price,
                    "inventory_management": "shopify",
                    "inventory_policy": "deny",
                }
            ],
        }
    }
    if image_urls:
        payload["product"]["images"] = [{"src": url} for url in image_urls]

    return payload


def create_shopify_product(payload, access_token):
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json",
    }
    resp = requests.post(f"{get_shopify_base_url()}/products.json", headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()["product"]


def set_inventory(access_token, location_id, inventory_item_id, quantity):
    """Naya product banne ke baad actual stock set karta hai -
    create-time 'inventory_quantity' field Shopify ignore kar deta hai,
    isliye ye alag call zaroori hai."""
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json",
    }
    payload = {
        "location_id": location_id,
        "inventory_item_id": inventory_item_id,
        "available": quantity,
    }
    resp = requests.post(f"{get_shopify_base_url()}/inventory_levels/set.json", headers=headers, json=payload, timeout=30)
    resp.raise_for_status()


def mark_pushed(sb, product_id, shopify_product, in_stock):
    variant = shopify_product["variants"][0]
    sb.table("products").update({
        "pushed_to_shopify": True,
        "shopify_product_id": str(shopify_product["id"]),
        "shopify_variant_id": str(variant["id"]),
        "shopify_inventory_item_id": str(variant["inventory_item_id"]),
        "shopify_status": shopify_product.get("status", "active"),
        "last_synced_price_inr": variant["price"],
        "last_synced_in_stock": in_stock,
        "shopify_pushed_at": datetime.now(timezone.utc).isoformat(),
        "shopify_synced_at": datetime.now(timezone.utc).isoformat(),
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

    location_id = get_default_location_id(access_token)
    print(f"Default location: {location_id}")

    print(f"{len(pending)} products push kar rahe hain Shopify pe (LIVE + PUBLISHED)...")

    summary = {"pushed": 0, "errors": 0}

    for p in pending:
        try:
            payload = build_shopify_payload(p)
            shopify_product = create_shopify_product(payload, access_token)

            in_stock = bool(p.get("in_stock"))
            quantity = 10 if in_stock else 0
            variant = shopify_product["variants"][0]
            set_inventory(access_token, location_id, variant["inventory_item_id"], quantity)

            mark_pushed(sb, p["id"], shopify_product, in_stock)
            summary["pushed"] += 1
            img_count = len(shopify_product.get("images", []))
            published = shopify_product.get("published_at") is not None
            print(f"  [OK] {p.get('name')} -> Shopify ID {shopify_product['id']} (stock: {quantity}, images: {img_count}, published: {published})")
        except Exception as e:
            summary["errors"] += 1
            print(f"  [ERROR] {p.get('name')}: {e}")

        time.sleep(RATE_LIMIT_DELAY)

    print("\n=== Summary ===")
    print(summary)


if __name__ == "__main__":
    run()
