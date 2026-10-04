"""
remove_kicksmachine.py

One-time cleanup - kicksmachine Jeet ka apna B2B sourcing partner
platform hai, galti se competitor-scrape source ki tarah add ho gaya
tha. Ye script uska poora data hata deta hai:
1. Jo bhi kicksmachine products Shopify pe live hain, unhe DELETE
   karta hai (Shopify API se)
2. Supabase se saari kicksmachine rows delete karta hai (chahe
   pushed the ya nahi)

Requires GitHub Secrets:
    SHOPIFY_STORE_DOMAIN, SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET,
    SUPABASE_URL, SUPABASE_SERVICE_KEY

Usage:
    DRY_RUN=1 python remove_kicksmachine.py   # sirf ginti, kuch delete nahi
    DRY_RUN=0 BATCH_SIZE=1000 python remove_kicksmachine.py

NOTE (2026-10-04): Pehla version ek batch ke baad BAAKI saari
kicksmachine rows Supabase se uda deta tha - chahe unka Shopify product
delete hua ho ya nahi. 5,001 rows aur 2,600 ke batch pe ~2,400 products
Shopify pe reh jaate, aur unka shopify_product_id bhi kho jaata. Ab:
- Supabase row SIRF tab delete hoti hai jab uska Shopify product delete
  ho chuka ho (ya Shopify pe pehle se nahi tha)
- Batches loop mein chalte hain jab tak kuch na bache (TIME_BUDGET tak)
- Aakhir mein Shopify pe vendor "Kicksmachine" wale bache products (jinki
  Supabase row pehle hi ud chuki thi - pichhle run ke ~161) bhi hat'te hain
- DRY_RUN default ON hai - delete ke liye DRY_RUN=0 dena padta hai
Dobara chalana safe hai - jahan ruka wahin se aage badhta hai.
"""
import os
import time
import requests
from supabase import create_client

BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "1000"))
RATE_LIMIT_DELAY = 0.6
API_VERSION = "2025-01"
SITE = "kicksmachine"
SHOPIFY_VENDOR = "Kicksmachine"  # shopify_push.py: vendor = brand.title()
DRY_RUN = os.environ.get("DRY_RUN", "1") != "0"
TIME_BUDGET = int(os.environ.get("TIME_BUDGET_SECONDS", "6600"))  # workflow timeout (120 min) se pehle ruko
MAX_CONSECUTIVE_ERRORS = 10
MAX_TOTAL_ERRORS = 50


def get_supabase():
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)


def get_shopify_domain():
    return os.environ["SHOPIFY_STORE_DOMAIN"]


def get_access_token():
    client_id = os.environ["SHOPIFY_CLIENT_ID"]
    client_secret = os.environ["SHOPIFY_CLIENT_SECRET"]
    resp = requests.post(
        f"https://{get_shopify_domain()}/admin/oauth/access_token",
        json={"client_id": client_id, "client_secret": client_secret, "grant_type": "client_credentials"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def get_shopify_base_url():
    return f"https://{get_shopify_domain()}/admin/api/{API_VERSION}"


def delete_shopify_product(access_token, product_id, retries=3):
    headers = {"X-Shopify-Access-Token": access_token}
    resp = requests.delete(f"{get_shopify_base_url()}/products/{product_id}.json", headers=headers, timeout=30)
    if resp.status_code == 404:
        return  # already deleted / never existed - fine
    if resp.status_code == 429 and retries > 0:
        time.sleep(float(resp.headers.get("Retry-After", "2")))
        return delete_shopify_product(access_token, product_id, retries - 1)
    resp.raise_for_status()


def shopify_vendor_ids(access_token):
    """Shopify pe abhi bhi bache vendor=Kicksmachine products ke ids (max 250)."""
    headers = {"X-Shopify-Access-Token": access_token}
    resp = requests.get(
        f"{get_shopify_base_url()}/products.json",
        headers=headers,
        params={"vendor": SHOPIFY_VENDOR, "fields": "id", "limit": 250},
        timeout=30,
    )
    resp.raise_for_status()
    return [p["id"] for p in resp.json()["products"]]


def shopify_vendor_count(access_token):
    headers = {"X-Shopify-Access-Token": access_token}
    resp = requests.get(f"{get_shopify_base_url()}/products/count.json",
                        headers=headers, params={"vendor": SHOPIFY_VENDOR}, timeout=30)
    resp.raise_for_status()
    return resp.json()["count"]


def supabase_count(sb, with_shopify_id=False):
    q = sb.table("products").select("id", count="exact").eq("site", SITE)
    if with_shopify_id:
        q = q.not_.is_("shopify_product_id", "null")
    return q.limit(1).execute().count


def run():
    sb = get_supabase()
    access_token = get_access_token()
    started = time.time()

    print(f"Supabase rows: {supabase_count(sb)} (Shopify id wali: {supabase_count(sb, True)}), "
          f"Shopify vendor={SHOPIFY_VENDOR}: {shopify_vendor_count(access_token)}")
    if DRY_RUN:
        print("DRY RUN - kuch delete nahi kiya. Asli delete ke liye DRY_RUN=0.")
        return

    deleted = orphans = errors = consecutive_errors = 0
    failed = set()  # is run mein fail hue - dobara mat uthao, warna loop atak jaata

    def should_stop():
        return (time.time() - started >= TIME_BUDGET
                or consecutive_errors >= MAX_CONSECUTIVE_ERRORS
                or errors >= MAX_TOTAL_ERRORS)

    # 1) Supabase rows jinka Shopify product hai: pehle Shopify, phir row
    while not should_stop():
        q = (sb.table("products").select("id,shopify_product_id")
             .eq("site", SITE).not_.is_("shopify_product_id", "null"))
        if failed:
            q = q.not_.in_("id", list(failed))
        batch = q.limit(BATCH_SIZE).execute().data
        if not batch:
            break
        for p in batch:
            if should_stop():
                break
            try:
                delete_shopify_product(access_token, p["shopify_product_id"])
                sb.table("products").delete().eq("id", p["id"]).execute()
                deleted += 1
                consecutive_errors = 0
            except Exception as e:
                errors += 1
                consecutive_errors += 1
                failed.add(p["id"])
                print(f"  [ERROR] product id {p['id']} (shopify {p['shopify_product_id']}): {e}")
            time.sleep(RATE_LIMIT_DELAY)
        print(f"  ...Shopify+Supabase se deleted ab tak: {deleted}, errors: {errors}")

    # 2) Jo kabhi push hi nahi hui - Shopify pe kuch nahi, seedha Supabase se
    del_resp = sb.table("products").delete().eq("site", SITE).is_("shopify_product_id", "null").execute()
    print(f"Never-pushed rows Supabase se deleted: {len(del_resp.data or [])}")

    # 3) Shopify pe bache vendor=Kicksmachine products (Supabase row pehle hi ud chuki thi)
    while not should_stop():
        ids = [i for i in shopify_vendor_ids(access_token) if i not in failed]
        if not ids:
            break
        for pid in ids:
            if should_stop():
                break
            try:
                delete_shopify_product(access_token, pid)
                orphans += 1
                consecutive_errors = 0
            except Exception as e:
                errors += 1
                consecutive_errors += 1
                failed.add(pid)
                print(f"  [ERROR] orphan shopify {pid}: {e}")
            time.sleep(RATE_LIMIT_DELAY)
    print(f"Orphan Shopify products deleted: {orphans}")

    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS or errors >= MAX_TOTAL_ERRORS:
        print("Bohot errors - ruk gaye (token/permissions/rate-limit check karo).")
    print(f"\nKul deleted: {deleted} + {orphans} orphan, errors: {errors}")
    print(f"Ab bache - Supabase: {supabase_count(sb)}, Shopify vendor={SHOPIFY_VENDOR}: "
          f"{shopify_vendor_count(access_token)}  (0 nahi hai to workflow dobara chalao)")


if __name__ == "__main__":
    run()
