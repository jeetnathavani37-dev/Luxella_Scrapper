"""
shopify_push.py

Supabase 'products' table se new products ko Shopify (Luxella store) mein
push karta hai - Shopify Admin API (REST) ke through.

NOTE (2026-08-30): Client credentials grant (24h token), inventory
alag call se set hoti hai (create-time field Shopify ignore karta hai),
real description + multi-size variants bhejte hain (agar available
hain), status=active + published=true (Online Store pe live hone ke
liye dono zaroori hain).

NOTE (2026-08-30) #2: compare_at_price bhi bhejte hain ab - Shopify pe
crossed-out "anchor" price dikhta hai, discount ka feel dene ke liye.

NOTE (2026-08-30) #3: Location ID hardcode hai (87267410093) -
'read_locations' scope avoid karne ke liye.

NOTE (2026-09-01) #4: BADA speed fix - poori gallery (3-8 images)
create-request mein bhej rahe the, Shopify har image SYNCHRONOUSLY
fetch/validate karta hai create ke andar - isliye create call bohot
slow ho raha tha (~15 sec/product). Fix: sirf PEHLI image create pe
bhejte hain, baaki gallery shopify_image_backfill.py alag se add karta
hai.

NOTE (2026-09-01) #5: DOOSRA speed fix - multi-size products (jaise
AloYoga leggings, 6-8 sizes) ke liye HAR size ke liye alag
inventory_levels/set call kar rahe the, chahe wo size out-of-stock ho.
Discovery: naya product hamesha 0 stock se banta hai by default
(Shopify create-time inventory field ignore karta hai) - matlab
out-of-stock sizes ke liye call karne ki ZAROORAT HI NAHI, wo already
0 hain. Fix: sirf IN-STOCK sizes ke liye hi set_inventory call karte
hain ab, baaki skip. Isse multi-size products ke liye API calls kaafi
kam ho gaye (jaise 8-size product mein pehle 8 calls, ab sirf jitni
sizes actually in-stock hain utni hi).

Requires GitHub Secrets:
    SHOPIFY_STORE_DOMAIN, SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET

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
DEFAULT_LOCATION_ID = 87267410093  # Luxella store ka single location - hardcoded


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


def fetch_pending_products(sb, limit):
    resp = (
        sb.table("products")
        .select("id,sku,name,brand,category,currency,selling_price_inr,compare_at_price_inr,"
                 "image_url,image_urls,description,variants,in_stock,site")
        .eq("pushed_to_shopify", False)
        .not_.is_("selling_price_inr", "null")
        .not_.is_("name", "null")
        .neq("name", "")
        .limit(limit)
        .execute()
    )
    return resp.data


def get_first_image_url(p):
    """Sirf pehli image - create-time fast rakhne ke liye. Baaki gallery
    shopify_image_backfill.py alag se add karta hai."""
    urls = p.get("image_urls")
    if urls and isinstance(urls, list) and len(urls) > 0:
        return urls[0]
    return p.get("image_url")


def get_size_variants(p):
    """Distinct, valid size-variants nikalta hai (agar 2+ alag sizes
    hain) - price + compare_at ko formula se recalculate karta hai."""
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
            "compare_at_price_inr": pricing["compare_at_price_inr"],
            "in_stock": bool(v.get("in_stock")),
        })

    return result if len(result) > 1 else []


def build_shopify_payload(p):
    name = (p.get("name") or "").strip()
    brand = (p.get("brand") or p.get("site") or "luxella").strip()
    sku = (p.get("sku") or "").strip() or f"LX-{p['id']}"
    price = str(p.get("selling_price_inr") or "0")
    compare_at = p.get("compare_at_price_inr")
    category = (p.get("category") or "uncategorized").strip()
    first_image = get_first_image_url(p)
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
                "compare_at_price": str(sv["compare_at_price_inr"]) if sv["compare_at_price_inr"] else None,
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
                "compare_at_price": str(compare_at) if compare_at else None,
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
    if first_image:
        payload["product"]["images"] = [{"src": first_image}]  # sirf 1 - speed ke liye

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

    location_id = DEFAULT_LOCATION_ID
    print(f"Default location (hardcoded): {location_id}")

    print(f"{len(pending)} products push kar rahe hain Shopify pe (LIVE + PUBLISHED, fast mode)...")

    summary = {"pushed": 0, "errors": 0, "multi_size": 0, "inventory_calls_skipped": 0}

    for p in pending:
        try:
            payload, size_variants = build_shopify_payload(p)
            shopify_product = create_shopify_product(payload, access_token)

            shopify_variants = shopify_product["variants"]

            if size_variants:
                # Sirf IN-STOCK sizes ke liye call karo - out-of-stock
                # sizes already 0 hain by default (naya product hamesha
                # 0 stock se banta hai), unke liye call karna waste hai.
                for sv, shopify_v in zip(size_variants, shopify_variants):
                    if sv["in_stock"]:
                        set_inventory(access_token, location_id, shopify_v["inventory_item_id"], 10)
                        time.sleep(RATE_LIMIT_DELAY)
                    else:
                        summary["inventory_calls_skipped"] += 1
                summary["multi_size"] += 1
                overall_in_stock = any(sv["in_stock"] for sv in size_variants)
            else:
                in_stock = bool(p.get("in_stock"))
                if in_stock:
                    set_inventory(access_token, location_id, shopify_variants[0]["inventory_item_id"], 10)
                    time.sleep(RATE_LIMIT_DELAY)
                else:
                    summary["inventory_calls_skipped"] += 1
                overall_in_stock = in_stock

            mark_pushed(sb, p["id"], shopify_product, overall_in_stock)
            summary["pushed"] += 1
            size_info = f", sizes: {len(size_variants)}" if size_variants else ""
            print(f"  [OK] {p.get('name')} -> Shopify ID {shopify_product['id']}{size_info}")
        except Exception as e:
            summary["errors"] += 1
            print(f"  [ERROR] {p.get('name')}: {e}")

        time.sleep(RATE_LIMIT_DELAY)

    print("\n=== Summary ===")
    print(summary)


if __name__ == "__main__":
    run()
