"""
Supabase ke saath baat-cheet: purana data padhna, naya data compare karna,
aur sirf changes ko product_changes table me likhna.
"""
import os
import json
import time
import base64
from collections import Counter
from datetime import datetime, timezone
from supabase import create_client
from pricing import calculate_pricing

SUPABASE_URL = os.environ["SUPABASE_URL"].strip()
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"].strip()

try:
    payload_part = SUPABASE_KEY.split(".")[1]
    padded = payload_part + "=" * (-len(payload_part) % 4)
    decoded = json.loads(base64.urlsafe_b64decode(padded))
    print(f"[DEBUG] JWT ref (project id in key) = {decoded.get('ref')}")
    print(f"[DEBUG] JWT role = {decoded.get('role')}")
    print(f"[DEBUG] URL project id (from SUPABASE_URL) = {SUPABASE_URL.split('//')[1].split('.')[0]}")
except Exception as e:
    print(f"[DEBUG] could not decode JWT: {e}")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def get_existing_product(site, sku, product_url):
    """Pehle product_url se match (har product ka apna URL). Pehle sku se match
    karte the - lekin kai sites pe alag products ek hi sku share karte hain
    (frye ke saare "Pre-Loved" = "_used", beyondyoga/stevemadden ke colours
    same style-sku), to wo sab EK hi row ko har scrape pe overwrite karte the
    aur roz nakli price-change log hota tha (2026-10-04: 697 aise sku).
    sku fallback sirf un purani rows ke liye jinka product_url khaali hai."""
    if product_url:
        res = (supabase.table("products").select("*")
               .eq("site", site).eq("product_url", product_url).limit(1).execute())
        if res.data:
            return res.data[0]
        if not sku:
            return None
        res = (supabase.table("products").select("*")
               .eq("site", site).eq("sku", sku).is_("product_url", "null").limit(1).execute())
        return res.data[0] if res.data else None
    if not sku:
        return None
    res = supabase.table("products").select("*").eq("site", site).eq("sku", sku).limit(1).execute()
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


PRICE_FIELDS = ("price", "price_inr", "landed_cost_inr", "selling_price_inr", "compare_at_price_inr")


def _prepare(product):
    # Price 0 = free gift (GWP) ya scraper ko price mila hi nahi (GOAT pe AI extraction "0" deta hai).
    # Isko "price pata nahi" maano - warna pricing floor (Rs799) lagta tha aur roz nakli 34->0 drop log hota tha.
    if product.get("price") is not None and product["price"] <= 0:
        product = {**product, "price": None}

    pricing_fields = calculate_pricing(
        product.get("price"),
        product.get("category"),
        product.get("currency", "USD"),
        name=product.get("name"),
    )
    return {**product, **pricing_fields}


def save_product(product):
    product = _prepare(product)

    existing = get_existing_product(product["site"], product.get("sku"), product["product_url"])

    if existing is None:
        supabase.table("products").insert({
            **product,
            "last_checked_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
        return "new"

    if product.get("price") is None:
        # is scrape mein price nahi mila - purana (sahi) price aur pricing mat mitao
        product = {k: v for k, v in product.items() if k not in PRICE_FIELDS}

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


# --- Batch save (2026-10-04) -------------------------------------------------
# save_product() har product pe 2 HTTP calls karta hai (select + update, ~0.8s) -
# ~50k products ke saath scrape.yml har baar 60-min timeout pe cancel ho jaata
# tha aur baaki sites chhoot jaati thi. save_products() site ki saari rows EK
# baar (paged) padhta hai, memory mein compare karta hai, aur:
#   - naye products: bulk insert (200 ke chunk)
#   - jinka kuch nahi badla: sirf timestamps, bulk update (.in_ ids)
#   - jinka content badla: pehle jaisa individual update
#   - change logs: bulk insert
# Matching aur change-logic bilkul save_product() wala hi hai.

PAGE = 1000
CHUNK = 200
TIMESTAMP_ONLY = {"scraped_at"}  # har scrape pe badalta hai - iske liye full update nahi


def _same(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        return abs(float(a) - float(b)) < 1e-9
    return a == b


def fetch_site_rows(site):
    rows, last = [], 0
    while True:
        page = (supabase.table("products").select("*").eq("site", site)
                .gt("id", last).order("id").limit(PAGE).execute().data)
        rows += page
        if len(page) < PAGE:
            return rows
        last = page[-1]["id"]


def _bulk_insert(table, rows):
    # PostgREST bulk insert mein jo key kisi row mein missing ho wo NULL ban jaati hai (default nahi) -
    # isliye same key-set wali rows ka group bana ke insert karo.
    groups = {}
    for r in rows:
        groups.setdefault(frozenset(r), []).append(r)
    for group in groups.values():
        for i in range(0, len(group), CHUNK):
            supabase.table(table).insert(group[i:i + CHUNK]).execute()


def save_products(products, deadline=None):
    """Ek site ke products batch mein save karta hai. Return Counter: new / changed / unchanged /
    skipped_dupe_url / not_saved_deadline, aur har change type ka count ("change:price_decrease" ...)."""
    out = Counter()
    if not products:
        return out
    site = products[0]["site"]
    rows = fetch_site_rows(site)
    by_url = {r["product_url"]: r for r in rows if r.get("product_url")}
    by_sku_no_url = {r["sku"]: r for r in rows if r.get("sku") and not r.get("product_url")}
    by_sku_any = {r["sku"]: r for r in rows if r.get("sku")}

    now = datetime.now(timezone.utc).isoformat()
    inserts, touch_ids, change_logs, seen = [], [], [], set()

    for raw in products:
        if deadline and time.time() > deadline:
            out["not_saved_deadline"] += 1
            continue
        product = _prepare(raw)
        url, sku = product.get("product_url"), product.get("sku")
        key = url or ("sku", sku)
        if key in seen:
            out["skipped_dupe_url"] += 1
            continue
        seen.add(key)

        if url:
            existing = by_url.get(url) or (by_sku_no_url.pop(sku, None) if sku else None)
        else:
            existing = by_sku_any.get(sku) if sku else None

        if existing is None:
            inserts.append({**product, "last_checked_at": now})
            out["new"] += 1
            continue

        if product.get("price") is None:
            product = {k: v for k, v in product.items() if k not in PRICE_FIELDS}

        found = []
        old_price, new_price = existing.get("price"), product.get("price")
        if old_price is not None and new_price is not None and old_price != new_price:
            found.append(("price_decrease" if new_price < old_price else "price_increase", old_price, new_price))
        old_stock, new_stock = existing.get("in_stock"), product.get("in_stock")
        if old_stock is not None and new_stock is not None and old_stock != new_stock:
            found.append(("back_in_stock" if new_stock else "out_of_stock", old_stock, new_stock))
        for change_type, old, new in found:
            change_logs.append({"site": product["site"], "sku": sku, "product_url": product["product_url"],
                                "name": product.get("name"), "change_type": change_type,
                                "old_value": str(old), "new_value": str(new)})

        content_changed = any(not _same(existing.get(k), v) for k, v in product.items() if k not in TIMESTAMP_ONLY)
        if content_changed:
            supabase.table("products").update({**product, "last_checked_at": now}).eq("id", existing["id"]).execute()
            if url:
                by_url[url] = {**existing, **product}
        else:
            touch_ids.append(existing["id"])

        if found:
            out["changed"] += 1
            out.update(f"change:{c[0]}" for c in found)
        else:
            out["unchanged"] += 1

    _bulk_insert("products", inserts)
    for i in range(0, len(touch_ids), CHUNK):
        supabase.table("products").update({"last_checked_at": now, "scraped_at": now}).in_(
            "id", touch_ids[i:i + CHUNK]).execute()
    _bulk_insert("product_changes", change_logs)
    return out
