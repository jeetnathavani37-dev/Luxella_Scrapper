"""
Supabase ke saath baat-cheet: purana data padhna, naya data compare karna,
aur sirf changes ko product_changes table me likhna.
"""
import os
from datetime import datetime, timezone
from supabase import create_client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]  # service role key (RLS bypass karne ke liye)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def get_existing_product(site, sku, product_url):
    """Purana record dhoondo agar hai to (price/stock compare karne ke liye)."""
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
    """
    Ek product ko save karta hai:
    - agar naya hai -> products table me insert
    - agar pehle se hai aur price/stock badla -> update + product_changes me log
    - agar kuch nahi badla -> sirf last_checked_at update
    """
    existing = get_existing_product(product["site"], product.get("sku"), product["product_url"])

    if existing is None:
        # bilkul naya product
        supabase.table("products").insert({
            **product,
            "last_checked_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        return "new"

    changes_found = []

    # price change check
    old_price = existing.get("price")
    new_price = product.get("price")
    if old_price is not None and new_price is not None and old_price != new_price:
        change_type = "price_decrease" if new_price < old_price else "price_increase"
        log_change(product["site"], product.get("sku"), product["product_url"],
                   product.get("name"), change_type, old_price, new_price)
        changes_found.append(change_type)

    # stock change check
    old_stock = existing.get("in_stock")
    new_stock = product.get("in_stock")
    if old_stock is not None and new_stock is not None and old_stock != new_stock:
        change_type = "back_in_stock" if new_stock else "out_of_stock"
        log_change(product["site"], product.get("sku"), product["product_url"],
                   product.get("name"), change_type, old_stock, new_stock)
        changes_found.append(change_type)

    # products table update (chahe change ho ya na ho, last_checked_at to update hoga)
    supabase.table("products").update({
        **product,
        "last_checked_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", existing["id"]).execute()

    return changes_found if changes_found else "unchanged"
