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
the.

NOTE (2026-08-30) #4: User ne decide kiya ki products ab directly LIVE
(status="active") jaayenge, draft mein nahi rukenge.

NOTE (2026-08-30) #5: status="active" hone ke bawajood product Online
Store par nahi dikhta jab tak "published": true na ho - dono alag
cheezein hain Shopify mein. Fix add kiya.

NOTE (2026-08-30) #6: Ab REAL description (Supabase 'description' field,
jo source site se scrape hoti hai) use karte hain, boilerplate text ki
jagah - agar available hai. Aur Ab MULTIPLE SIZES support hai - agar
product ke paas 'variants' array hai (2+ distinct sizes), Shopify pe
"Size" option ke saath multi-variant product banta hai (customer size
choose kar sakta hai), sirf ek size nahi. Har size variant ka apna price
(same pricing formula se calculate hota hai) aur stock hota hai.
NOTE: shopify_sync.py abhi bhi sirf PEHLE variant ka price/stock sync
karta hai (multi-variant sync ek bada alag kaam hai, abhi scope se
bahar) - baaki sizes creation ke time hi set ho jaate hain, baad mein
automatically update nahi hote.

Requires GitHub Secrets:
    SHOPIFY_STORE_DOMAIN     = luxella-9299.myshopify.com
    SHOPIFY_CLIENT_ID        = Dev Dashboard app ka Client ID
    SHOPIFY_CLIENT_SECRET    = Dev Dashboard app ka Client secret

Usage:
    BATCH_SIZE=200 python shopify_push.py
"""
import os
import re
import time
import requests
from datetime import datetime, timezone
from supabase import create_client
from pricing import calculate_pricing

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
        .select("id,sku,name,brand,category,currency,selling_price_inr,image_url,"
                 "image_urls,description,variants,in_stock,site")
        .eq("pushed_to_shopify", False)
        .not_.is_("selling_price_inr", "null")
        .not_.is_("name", "null")
        .neq("name", "")
        .limit(limit)
        .execute()
    )
    return resp.data


def get_all_image_urls(p):
    urls = p.get("image_urls")
    if urls and isinstance(urls, list) and len(urls) > 0:
        return urls
    single = p.get("image_url")
    return [single] if single else []


def get_size_variants(p):
    """Distinct, valid size-variants nikalta hai (agar 2+ alag sizes
    hain) - price ko selling-price formula se recalculate karta hai
    (raw scraped price se, taaki margin consistent rahe)."""
    raw_variants = p.get("variants")
    if not raw_variants or not isinstance(raw_variants, list):
        return []

    category = p.get("category")
    currency = p.get("currency", "USD")
    name = p.get("name")

    seen_sizes = set()
    result = []
    for v in raw_variants:
        size = v.get("size")
        if not size or size in seen_sizes:
            continue
        if v.get("price") is None:
            continue
        seen_sizes.add(size)
        pricing = calculate_pricing(v["price"], category, currency, name=name)
        result.append({
            "size": size,
            "sku": v.get("sku"),
            "selling_price_inr": pricing["selling_price_inr"],
            "in_stock": bool(v.get("in_stock")),
        })

    return result if len(result) > 1 else []


def build_shopify_payload(p):
    name = (p.get("name") or "").strip()
    brand = (p.get("brand") or p.get("site") or "luxella").strip()
    sku = (p.get("sku") or "").strip() or f"LX-{p['id']}"
    price = str(p.get("selling_price_inr") or "0")
    category = (p.get("category") or "uncategorized").strip()
    image_urls = get_all_image_urls(p)
    description = p.get("description")

    title = f"{brand.title()} {name}".strip()[:255]
    body_html = description if description else f"<p>{title}</p><p>Sourced via Luxella.</p>"

    size_variants = get_size_variants(p)

    if size_variants:
        variants_payload = [
            {
                "option1": sv["size"],
                "sku": sv["sku"] or f"LX-{p['id']}-{sv['size']}",
                "price": str(sv["selling_price_inr"]),
                "inventory_management": "shopify",
                "inventory_policy": "deny",
            }
            for sv in size_variants
        ]
        options_payload = [{"name": "Size", "values": [sv["size"] for sv in size_variants]}]
    else:
        variants_payload = [
            {
                "sku": sku,
                "price": price,
                "inventory_management": "shopify",
                "inventory_policy": "deny",
            }
        ]
        options_payload = None

    payload = {
        "product": {
            "title": title,
            "body_html": body_html,
            "vendor": brand.title(),
            "product_type": category.title(),
            "tags": f"{brand}, {category}",
            "status": "active",
            "published": True,
            "variants": variants_payload,
        }
    }
    if options_payload:
        payload["product"]["options"] = options_payload
    if image_urls:
        payload["product"]["images"] = [{"src": url} for url in image_urls]

    return payload, size_variants


def create_shopify_product(payload, access_token):
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json",
    }
    resp = requests.post(f"{get_shopify_base_url()}/products.json", headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()["product"]


def set_inventory(access_token, location_id, inventory_item_id, quantity):
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
    """Sync-compat ke liye pehle variant ke IDs/price store karte hain
    (shopify_sync.py abhi sirf single-variant sync support karta hai)."""
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

    summary = {"pushed": 0, "errors": 0, "multi_size": 0}

    for p in pending:
        try:
            payload, size_variants = build_shopify_payload(p)
            shopify_product = create_shopify_product(payload, access_token)

            shopify_variants = shopify_product["variants"]

            if size_variants:
                # har size variant ka apna stock set karo (order same rehta hai jo payload mein bheja tha)
                for sv, shopify_v in zip(size_variants, shopify_variants):
                    qty = 10 if sv["in_stock"] else 0
                    set_inventory(access_token, location_id, shopify_v["inventory_item_id"], qty)
                    time.sleep(RATE_LIMIT_DELAY)
                summary["multi_size"] += 1
                overall_in_stock = any(sv["in_stock"] for sv in size_variants)
            else:
                in_stock = bool(p.get("in_stock"))
                quantity = 10 if in_stock else 0
                set_inventory(access_token, location_id, shopify_variants[0]["inventory_item_id"], quantity)
                overall_in_stock = in_stock

            mark_pushed(sb, p["id"], shopify_product, overall_in_stock)
            summary["pushed"] += 1
            img_count = len(shopify_product.get("images", []))
            size_info = f", sizes: {len(size_variants)}" if size_variants else ""
            print(f"  [OK] {p.get('name')} -> Shopify ID {shopify_product['id']} (images: {img_count}{size_info})")
        except Exception as e:
            summary["errors"] += 1
            print(f"  [ERROR] {p.get('name')}: {e}")

        time.sleep(RATE_LIMIT_DELAY)

    print("\n=== Summary ===")
    print(summary)


if __name__ == "__main__":
    run()
