"""
shopify_sync.py

Un products ka price/stock/compare-at-price Shopify pe UPDATE karta hai
jo already push ho chuke hain (naye products create nahi karta - wo
shopify_push.py karta hai).

NOTE (2026-08-30): compare_at_price (MRP/anchor - crossed-out price)
sync bhi add kiya - purane products ko bhi mil jaayega.

NOTE (2026-08-30) #2: Location ID ab HARDCODE hai (87267410093) -
pehle GET /locations.json se fetch karte the, jisko 'read_locations'
scope chahiye tha jo humare app mein nahi tha (403 aa raha tha baar
baar, scope add karne ki koshish bhi kaam nahi aayi). Fix: location ID
ek baar Shopify MCP connector se nikaal ke hardcode kar diya - store
mein sirf ek hi location hai (single-location business), isliye ye
change hone ka risk nahi hai. Agar kabhi naya location add ho ya ye ID
change ho, yahan manually update karna padega.

NOTE (2026-09-02): run() ab kitne products actually CHANGE hue (price/
stock update) wo count return karta hai (0 nahi) - taaki
auto_pilot.py (jo push+sync+image-backfill ko continuous loop mein
chalata hai jab tak sab kuch complete na ho jaaye) pata laga sake ki
sync mein abhi bhi meaningful kaam bacha hai ya nahi.

Requires GitHub Secrets:
    SHOPIFY_STORE_DOMAIN, SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET

Usage:
    BATCH_SIZE=300 python shopify_sync.py
"""
import os
import time
import requests
from datetime import datetime, timezone
from supabase import create_client

BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "300"))
RATE_LIMIT_DELAY = 0.6
API_VERSION = "2025-01"
DEFAULT_LOCATION_ID = 87267410093  # Luxella store ka single location - hardcoded (read_locations scope avoid karne ke liye)


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
    resp = requests.post(
        f"https://{domain}/admin/oauth/access_token",
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


def fetch_synced_products(sb, limit):
    """Already-pushed products, sabse purane-synced pehle (rotation)."""
    resp = (
        sb.table("products")
        .select("id,name,selling_price_inr,compare_at_price_inr,in_stock,shopify_variant_id,"
                 "shopify_inventory_item_id,last_synced_price_inr,last_synced_compare_at_price_inr,"
                 "last_synced_in_stock")
        .eq("pushed_to_shopify", True)
        .order("shopify_synced_at", desc=False, nullsfirst=True)
        .limit(limit)
        .execute()
    )
    return resp.data


def update_variant(access_token, variant_id, price, compare_at_price):
    """Price aur compare_at_price dono ek hi API call mein update karta hai."""
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json",
    }
    variant_payload = {"id": variant_id, "price": str(price)}
    if compare_at_price:
        variant_payload["compare_at_price"] = str(compare_at_price)
    payload = {"variant": variant_payload}
    resp = requests.put(f"{get_shopify_base_url()}/variants/{variant_id}.json", headers=headers, json=payload, timeout=30)
    resp.raise_for_status()


def update_stock(access_token, location_id, inventory_item_id, quantity):
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json",
    }
    payload = {"location_id": location_id, "inventory_item_id": inventory_item_id, "available": quantity}
    resp = requests.post(f"{get_shopify_base_url()}/inventory_levels/set.json", headers=headers, json=payload, timeout=30)
    resp.raise_for_status()


def mark_synced(sb, product_id, price, compare_at_price, in_stock):
    sb.table("products").update({
        "last_synced_price_inr": price,
        "last_synced_compare_at_price_inr": compare_at_price,
        "last_synced_in_stock": in_stock,
        "shopify_synced_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", product_id).execute()


def run():
    sb = get_supabase()
    products = fetch_synced_products(sb, BATCH_SIZE)

    if not products:
        print("Koi pushed products nahi mile sync karne ke liye.")
        return 0

    print("Access token generate kar rahe hain...")
    access_token = get_access_token()
    location_id = DEFAULT_LOCATION_ID
    print(f"Token mil gaya. Location (hardcoded): {location_id}")

    print(f"{len(products)} products check kar rahe hain price/stock/MRP changes ke liye...")

    summary = {"price_updated": 0, "stock_updated": 0, "unchanged": 0, "errors": 0}

    for p in products:
        try:
            current_price = p.get("selling_price_inr")
            current_compare_at = p.get("compare_at_price_inr")
            current_stock = bool(p.get("in_stock"))

            last_price = p.get("last_synced_price_inr")
            last_compare_at = p.get("last_synced_compare_at_price_inr")
            last_stock = p.get("last_synced_in_stock")

            variant_id = p.get("shopify_variant_id")
            inventory_item_id = p.get("shopify_inventory_item_id")

            if not variant_id or not inventory_item_id:
                print(f"  [SKIP] {p.get('name')}: variant/inventory ID missing (purana push, re-push zaroori hai)")
                mark_synced(sb, p["id"], current_price, current_compare_at, current_stock)
                continue

            changed = False

            price_changed = (
                current_price is not None
                and (last_price is None or float(current_price) != float(last_price))
            )
            compare_at_changed = (
                current_compare_at is not None
                and (last_compare_at is None or float(current_compare_at) != float(last_compare_at))
            )
            if price_changed or compare_at_changed:
                update_variant(access_token, variant_id, current_price, current_compare_at)
                print(f"  [PRICE] {p.get('name')}: price {last_price}->{current_price}, "
                      f"MRP {last_compare_at}->{current_compare_at}")
                summary["price_updated"] += 1
                changed = True
                time.sleep(RATE_LIMIT_DELAY)

            stock_changed = (last_stock is None or current_stock != last_stock)
            if stock_changed:
                quantity = 10 if current_stock else 0
                update_stock(access_token, location_id, inventory_item_id, quantity)
                print(f"  [STOCK] {p.get('name')}: {last_stock} -> {current_stock} (qty={quantity})")
                summary["stock_updated"] += 1
                changed = True
                time.sleep(RATE_LIMIT_DELAY)

            if not changed:
                summary["unchanged"] += 1

            mark_synced(sb, p["id"], current_price, current_compare_at, current_stock)

        except Exception as e:
            summary["errors"] += 1
            print(f"  [ERROR] {p.get('name')}: {e}")

        time.sleep(RATE_LIMIT_DELAY)

    print("\n=== Summary ===")
    print(summary)
    return summary["price_updated"] + summary["stock_updated"]


if __name__ == "__main__":
    run()
