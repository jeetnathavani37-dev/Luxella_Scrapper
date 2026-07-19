"""
Supabase ke saath baat-cheet: purana data padhna, naya data compare karna,
aur sirf changes ko product_changes table me likhna.
"""
import os
import json
import base64
from datetime import datetime, timezone
from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"].strip()
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"].strip()

# ---- DIAGNOSTIC: key ke andar chhupi info dekhte hain (safe, non-sensitive) ----
try:
    payload_part = SUPABASE_KEY.split(".")[1]
    padded = payload_part + "=" * (-len(payload_part) % 4)
    decoded = json.loads(base64.urlsafe_b64decode(padded))
    print(f"[DEBUG] JWT ref (project id in key) = {decoded.get('ref')}")
    print(f"[DEBUG] JWT role = {decoded.get('role')}")
    print(f"[DEBUG] URL project id (from SUPABASE_URL) = {SUPABASE_URL.split('//')[1].split('.')[0]}")
except Exception as e:
    print(f"[DEBUG] could not decode JWT: {e}")
# --------------------------------------------------------------------------------

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def get_existing_product(site, sku, product_url):
    query = supabase.table("products").select("*").eq("site", site)
    if sku:
        query = query.eq("sku", sku)
    else:
        query = query.eq("product_url", product_url)
    res = query.execute()
    return res.data[0] if res.data else None


def log_change(site, sku, product_url, name, change_type, old_value, new_value):
    supabase.table("product_changes").insert({
        "site": site,
        "sku": sku,
        "product_url": product_url,
        "name": name,
        "change_type": change_type,
        "old_value": str(old_value),
        "new_value": str(new_value),
    }).execute()


def save_product(product):
    existing = get_existing_product(product["site"], product.get("sku"), product["product_url"])

    if existing is None:
        supabase.table("products").insert({
            **product,
            "last_checked_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        return "new"

    changes_found = []
    old_price = existing.get("price")
    new_price = product.get("price")
    if old_price is not None and new_price is not None and old_price != new_price:
        change_type = "price_decrease" if new_price < old_price else "price_increase"
        log_change(product["site"], product.get("sku"), product["product_url"],
                   product.get("name"), change_type, old_price, new_price)
        changes_found.append(change_type)

    old_stock = existing.get("in_stock")
    new_stock = product.get("in_stock")
    if old_stock is not None and new_stock is not None and old_stock != new_stock:
        change_type = "back_in_stock" if new_stock else "out_of_stock"
        log_change(product["site"], product.get("sku"), product["product_url"],
                   product.get("name"), change_type, old_stock, new_stock)
        changes_found.append(change_type)

    supabase.table("products").update({
        **product,
        "last_checked_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", existing["id"]).execute()

    return changes_found if changes_found else "unchanged"
