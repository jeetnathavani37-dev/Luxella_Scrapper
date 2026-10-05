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

NOTE (2026-10-04): source `price` 0 wale products ka price Shopify pe nahi
bhejte aur stock 0 kar dete hain (pehle Rs799 floor price pe in-stock dikhte the).

NOTE (2026-09-28): fetch_synced_products() ab stock-mismatch wale products
PEHLE uthata hai (source pe sold out lekin Shopify pe abhi bhi in-stock,
aur ulta). Pehle sirf shopify_synced_at rotation tha - ~48k products mein
haal hi mein synced product ka sold-out hona poori rotation (kai din) tak
Shopify pe nahi pahunchta tha, customer order kar sakta tha.

Requires GitHub Secrets:
    SHOPIFY_STORE_DOMAIN, SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET

Usage:
    BATCH_SIZE=300 python shopify_sync.py
"""
import json
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
    """Already-pushed products. Pehle wo jinka stock Shopify se mismatch hai
    (source pe sold out lekin Shopify pe in-stock, phir wapas-in-stock),
    baaki batch sabse purane-synced se bharo (rotation)."""
    def base():
        return (
            sb.table("products")
            .select("id,name,price,selling_price_inr,compare_at_price_inr,in_stock,shopify_variant_id,"
                    "shopify_inventory_item_id,last_synced_price_inr,last_synced_compare_at_price_inr,"
                    "last_synced_in_stock,shopify_product_id,variants,last_synced_variant_stock")
            .eq("pushed_to_shopify", True)
        )

    urgent = base().eq("in_stock", False).eq("last_synced_in_stock", True).order("id").limit(limit).execute().data
    if len(urgent) < limit:
        urgent += base().eq("in_stock", True).eq("last_synced_in_stock", False).order("id").limit(limit - len(urgent)).execute().data
    if len(urgent) >= limit:
        return urgent

    seen = {p["id"] for p in urgent}
    rotation = base().order("shopify_synced_at", desc=False, nullsfirst=True).order("id").limit(limit).execute().data
    return urgent + [p for p in rotation if p["id"] not in seen][:limit - len(urgent)]


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


def mark_synced(sb, product_id, price, compare_at_price, in_stock, variant_sig=None):
    row = {
        "last_synced_price_inr": price,
        "last_synced_compare_at_price_inr": compare_at_price,
        "last_synced_in_stock": in_stock,
        "shopify_synced_at": datetime.now(timezone.utc).isoformat(),
    }
    if variant_sig is not None:
        row["last_synced_variant_stock"] = variant_sig
    sb.table("products").update(row).eq("id", product_id).execute()


# --- Per-size stock (2026-10-05) ---------------------------------------------
# update_stock() sirf pehle variant (shopify_inventory_item_id) ko chhoota tha - multi-size
# products ka source pe sold out hona Shopify pe sirf pehla size 0 karta tha, baaki sizes 10 pe
# bikte rehte the (~9,151 products). Ye helpers har size ka target nikalte hain. Spec:
# docs/specs/2026-10-05-sync-all-sizes.md
SIZE_IN_STOCK_QTY = 10


def _size_stock(p):
    """{size: in_stock} - wahi sizes jo push ne banaye the (shopify_push.get_size_variants: dedup, price wale)."""
    from shopify_push import get_size_variants
    return {str(sv["size"]).strip(): bool(sv["in_stock"]) for sv in get_size_variants(p)}


def _price_ok(p):
    # NOTE: product-level `in_stock` scraper mein PEHLE size se aata hai - multi-size ke liye
    # use mat karo (2026-10-05: is galti se 2 sandals ke available sizes 0 ho gaye the).
    return bool(p.get("price")) and float(p["price"]) > 0


def stock_signature(p):
    """Product + har size ka stock ek string mein - badla to hi Shopify call. None = single-size product."""
    sizes = _size_stock(p)
    if not sizes:
        return None
    return json.dumps({"price_ok": _price_ok(p), "sizes": sorted(sizes.items())}, separators=(",", ":"))


def size_targets(p, shopify_variants):
    """shopify_variants: [{"inventory_item_id", "size" (option1), "available"}].
    Return (changes, skipped, unmatched):
      changes   = [(inventory_item_id, current, target)] - sirf jahan current 0/10 hai aur target alag
      skipped   = [(inventory_item_id, size, current)] - 1..9 (customer orders ke baad) - inhe mat chhuo
      unmatched = [size] - Shopify pe hai par scrape mein nahi - inhe CHHOOTE NAHI (label change ho sakta hai)"""
    price_ok = _price_ok(p)
    sizes = _size_stock(p)
    changes, skipped, unmatched = [], [], []
    for v in shopify_variants:
        size, current = str(v.get("size") or "").strip(), v.get("available")
        if size not in sizes:
            unmatched.append(size)
            continue
        target = SIZE_IN_STOCK_QTY if (price_ok and sizes[size]) else 0
        if current == target:
            continue
        if current not in (0, SIZE_IN_STOCK_QTY):
            skipped.append((v["inventory_item_id"], size, current))
            continue
        changes.append((v["inventory_item_id"], current, target))
    return changes, skipped, unmatched


# Inventory GraphQL: changeFromQuantity (compare-and-swap) naye API version mein hai; REST 2025-01 pe hi rehta hai
GRAPHQL_API_VERSION = os.environ.get("SHOPIFY_GRAPHQL_API_VERSION", "2026-07")
LOCATION_GID = f"gid://shopify/Location/{DEFAULT_LOCATION_ID}"


def shopify_graphql(access_token, query, variables=None, tries=5):
    url = f"https://{get_shopify_domain()}/admin/api/{GRAPHQL_API_VERSION}/graphql.json"
    headers = {"X-Shopify-Access-Token": access_token, "Content-Type": "application/json"}
    for attempt in range(tries):
        resp = requests.post(url, headers=headers, json={"query": query, "variables": variables or {}}, timeout=60)
        if resp.status_code == 429:
            time.sleep(2 * (attempt + 1))
            continue
        resp.raise_for_status()
        body = resp.json()
        errors = body.get("errors") or []
        if any((e.get("extensions") or {}).get("code") == "THROTTLED" for e in errors):
            time.sleep(2 * (attempt + 1))
            continue
        if errors:
            raise RuntimeError(f"GraphQL errors: {errors}")
        return body["data"]
    raise RuntimeError("Shopify GraphQL throttled - retries khatam")


def fetch_shopify_sizes(access_token, product_id):
    """[{inventory_item_id, size (option1), available}] - REST, ek product."""
    headers = {"X-Shopify-Access-Token": access_token}
    resp = requests.get(f"{get_shopify_base_url()}/products/{product_id}.json?fields=variants", headers=headers, timeout=30)
    resp.raise_for_status()
    return [{"inventory_item_id": v["inventory_item_id"], "size": v.get("option1"), "available": v.get("inventory_quantity")}
            for v in resp.json()["product"]["variants"]]


# 2026-04+ API: inventorySetQuantities ko @idempotent key chahiye (bina iske har write fail)
SET_QTY_MUTATION = """mutation($input: InventorySetQuantitiesInput!, $idempotencyKey: String!) {
  inventorySetQuantities(input: $input) @idempotent(key: $idempotencyKey) { userErrors { field message code } } }"""


class StaleQuantity(Exception):
    """CAS fail - beech mein stock badla (jaise customer order). Is product ko chhodo, agle run mein dobara."""


def set_size_quantities(access_token, changes, ref):
    """changes = [(inventory_item_id, current, target)] - CAS: current badal gaya ho to Shopify mana karega."""
    import uuid
    for i in range(0, len(changes), 250):
        chunk = changes[i:i + 250]
        # har operation nayi key (Shopify 24h tak key yaad rakhta hai - same key = change chupchaap skip).
        # shopify_graphql ke retries same variables bhejte hain, to ek request ke retries same key share karte hain.
        key = str(uuid.uuid4())
        data = shopify_graphql(access_token, SET_QTY_MUTATION, {"idempotencyKey": key, "input": {
            "name": "available", "reason": "correction", "referenceDocumentUri": ref,
            "quantities": [{"inventoryItemId": f"gid://shopify/InventoryItem/{iid}", "locationId": LOCATION_GID,
                            "quantity": target, "changeFromQuantity": current} for iid, current, target in chunk]}})
        errs = data["inventorySetQuantities"]["userErrors"]
        if errs and all(e.get("code") == "CHANGE_FROM_QUANTITY_STALE" for e in errs):
            raise StaleQuantity(f"{len(errs)} stale")
        if errs:
            raise RuntimeError(f"inventorySetQuantities: {errs[:3]}")


def sync_sizes(access_token, p):
    """Multi-size product ke saare sizes source se milao. Return (changes, skipped, unmatched, applied).
    applied=False = kuch nahi likha (size naam match nahi / CAS stale) - signature mat badlo, agle run dobara."""
    shop = fetch_shopify_sizes(access_token, p["shopify_product_id"])
    changes, skipped, unmatched = size_targets(p, shop)
    if unmatched and len(unmatched) * 2 >= len(shop):
        # zyada tar sizes match nahi = label badla (jaise "7" -> "US 7") - kuch mat likho
        print(f"  [SIZES-SKIP] {p.get('name')}: unmatched Shopify sizes {unmatched[:5]} - kuch nahi likha")
        return changes, skipped, unmatched, False
    if changes:
        try:
            set_size_quantities(access_token, changes, f"gid://luxella-scrapper/SizeSync/{p['id']}")
        except StaleQuantity:
            print(f"  [SIZES-STALE] {p.get('name')}: stock beech mein badla - agle run")
            return changes, skipped, unmatched, False
    return changes, skipped, unmatched, True


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
            # Source price 0 = parse fail / free item: Shopify pe floor price (Rs799) pe na bike -
            # price mat bhejo, stock 0 rakho.
            zero_price = not p.get("price") or float(p["price"]) <= 0
            current_stock = bool(p.get("in_stock")) and not zero_price

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
                not zero_price
                and current_price is not None
                and (last_price is None or float(current_price) != float(last_price))
            )
            compare_at_changed = (
                not zero_price
                and current_compare_at is not None
                and (last_compare_at is None or float(current_compare_at) != float(last_compare_at))
            )
            if price_changed or compare_at_changed:
                update_variant(access_token, variant_id, current_price, current_compare_at)
                print(f"  [PRICE] {p.get('name')}: price {last_price}->{current_price}, "
                      f"MRP {last_compare_at}->{current_compare_at}")
                summary["price_updated"] += 1
                changed = True
                time.sleep(RATE_LIMIT_DELAY)

            # Multi-size (2026-10-05): har size alag. Sirf jinka signature hai (repair_variant_stock.py ke baad
            # ya naye push) - null wale abhi purane pehle-variant raste pe, taaki sync bina dry-run sab na badal de.
            stored_sig = p.get("last_synced_variant_stock")
            new_sig = stock_signature(p) if stored_sig is not None else None
            if new_sig is not None:
                if new_sig != stored_sig:
                    ch, skipped, unmatched, applied = sync_sizes(access_token, p)
                    if not applied:
                        new_sig = stored_sig  # signature mat badlo - agle run dobara try
                    else:
                        print(f"  [SIZES] {p.get('name')}: {len(ch)} sizes changed, {len(skipped)} left (1-9), "
                              f"{len(unmatched)} unmatched (chhode)")
                        summary["sizes_updated"] = summary.get("sizes_updated", 0) + 1
                        changed = True
                    time.sleep(RATE_LIMIT_DELAY)
                stock_changed = False  # pehle-variant wala rasta multi-size pe nahi
            else:
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

            if zero_price:
                # last_synced_price ko purana hi rehne do - jab asli price wapas aaye to update chale
                mark_synced(sb, p["id"], last_price, last_compare_at, current_stock, new_sig)
            else:
                mark_synced(sb, p["id"], current_price, current_compare_at, current_stock, new_sig)

        except Exception as e:
            summary["errors"] += 1
            print(f"  [ERROR] {p.get('name')}: {e}")

        time.sleep(RATE_LIMIT_DELAY)

    print("\n=== Summary ===")
    print(summary)
    return summary["price_updated"] + summary["stock_updated"] + summary.get("sizes_updated", 0)


if __name__ == "__main__":
    run()
