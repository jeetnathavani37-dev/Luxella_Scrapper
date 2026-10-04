"""
Entry point. GitHub Actions se chalta hai.

NOTE (2026-09-02): BADA fix - 90+ sites hain, 60-min timeout ke andar
saari scrape nahi ho paati. Pehle SITES list fixed order mein process
hoti thi - shuru wali sites hamesha scrape hoti thi, end wali (jaise
aloyoga) hamesha timeout se pehle chhoot jaati thi. Fix: ab Supabase se
har site ka last scraped_at fetch karke, sabse purana-scraped pehle
process karte hain.

NOTE (2026-09-05): "kabhi-scrape-na-hui" aur "purani-scraped-but-kaam-
karti-hain" sites ko INTERLEAVE karte hain - har 2 "purani-stale" sites
ke baad 1 "kabhi-nahi" site try hoti hai.

NOTE (2026-09-13): "use_firecrawl": True routing add kiya.

NOTE (2026-10-04): Har run 60-min timeout pe CANCEL ho raha tha. Do wajah:
1. Har product 2 HTTP calls (~0.8s) - ab db.save_products() site-batch mein
   save karta hai (ek baar padho, bulk insert/update).
2. get_staleness_order() sirf 1000 rows padhta tha (PostgREST limit) - 60k
   mein se - isliye order galat tha. Ab id-paged poori table padhta hai.
Saath mein MAX_RUN_MINUTES (default 45, +5 min save grace) - itne minute baad nayi site shuru
nahi hoti, run khud saaf khatam hota hai (cancel hoke log/summary nahi khote).

NOTE (2026-09-28): SCRAPE_GROUP add kiya - Firecrawl credits (5 per
page) 17 Sept ke aas-paas khatam ho gaye the kyunki 37 Firecrawl sites
har 6 ghante chal rahi thi. Ab do alag groups hain:
  - SCRAPE_GROUP="free" (DEFAULT, env set na ho tab bhi): sirf woh sites
    jo Firecrawl use NAHI karti (Shopify brands etc.) - har 6 ghante wale
    scrape.yml ke liye. Isse purana scrape.yml bina edit kiye hi ab
    Firecrawl credits nahi jalata.
  - SCRAPE_GROUP="firecrawl": sirf Firecrawl sites, PAUSED list ke
    bahar wali - din mein 1 baar wale scrape-firecrawl.yml ke liye.
  - SCRAPE_GROUP="all": sab kuch (manual use ke liye).
ONLY_SITE set ho toh group aur paused dono ignore hote hain (manual
test ke liye), jaisa pehle tha.

PAUSED: woh Firecrawl sites jinme abhi tak ek bhi product nahi aaya -
inpe credits jalana band kiya. Ek-ek karke ONLY_SITE se test karke
list se hataana (jab credits/plan decide ho jaye).
"""
import os
import re
import time
from collections import Counter, defaultdict
from patchright.sync_api import sync_playwright
from supabase import create_client

from sites import SITES
from extract import scrape_site
from shopify_scraper import scrape_shopify
from scraperapi_scraper import scrape_site_scraperapi
from scrapegraph_scraper import scrape_site_scrapegraph
from firecrawl_scraper import scrape_site_firecrawl
from db import save_product, save_products

# Firecrawl sites jinse abhi tak koi data nahi aaya (2026-09-28 tak).
FIRECRAWL_PAUSED = {
    "longchamp", "jcrewfactory", "pandora", "dkny", "oakley", "biosilk",
    "disneystore", "orientaltrading", "funko", "kohls", "hoka", "gilt",
    "ruelala", "nordstromrack", "yoox", "flannels", "maisonette",
    "scheels", "thecode", "secretlabel",
}


def filter_by_group(sites):
    group = os.environ.get("SCRAPE_GROUP", "free").strip().lower()
    if group == "all":
        selected = list(sites)
    elif group == "firecrawl":
        selected = [
            s for s in sites
            if s.get("use_firecrawl") and s["name"] not in FIRECRAWL_PAUSED
        ]
    else:
        group = "free"
        selected = [s for s in sites if not s.get("use_firecrawl")]
    print(f"SCRAPE_GROUP={group}: {len(selected)} sites select hui.")
    return selected


def build_proxy_username(base_username, country):
    if not base_username:
        return base_username
    base = re.sub(r"-[a-z]{2}-\d+$", "", base_username.strip())
    if not country:
        return base
    return f"{base}-{country.lower()}-1"


def _block_heavy_resources(route):
    if route.request.resource_type in ("image", "media", "font"):
        route.abort()
    else:
        route.continue_()


def build_browser_context(playwright, config):
    launch_args = {"headless": True}
    needs_proxy = bool(config.get("needs_proxy"))

    if needs_proxy:
        proxy_server = os.environ.get("PROXY_SERVER")
        proxy_user = os.environ.get("PROXY_USERNAME")
        proxy_pass = os.environ.get("PROXY_PASSWORD")

        if proxy_server:
            country = config.get("proxy_country")
            resolved_user = build_proxy_username(proxy_user, country)
            launch_args["proxy"] = {
                "server": proxy_server,
                "username": resolved_user,
                "password": proxy_pass,
            }
            print(f"  [proxy] {config['name']} -> {resolved_user} ({country or 'no country'})")
        else:
            print(f"  [WARNING] {config['name']} ko proxy chahiye par PROXY_SERVER secret set nahi hai.")

    browser = playwright.chromium.launch(**launch_args)
    context = browser.new_context(
        viewport={"width": 1366, "height": 900},
        locale="en-US",
    )

    if needs_proxy:
        context.route("**/*", _block_heavy_resources)

    return browser, context


def get_staleness_order(sites):
    try:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_KEY"]
        sb = create_client(url, key)
        # PostgREST ek baar mein max 1000 rows deta hai - poori table id-paged padho
        all_rows, last_id = [], 0
        while True:
            page = (sb.table("products").select("id,site,scraped_at")
                    .gt("id", last_id).order("id").limit(1000).execute().data)
            all_rows += page
            if len(page) < 1000:
                break
            last_id = page[-1]["id"]

        last_scraped = defaultdict(lambda: None)
        for row in all_rows:
            site_name = row.get("site")
            ts = row.get("scraped_at")
            if site_name and ts:
                if last_scraped[site_name] is None or ts > last_scraped[site_name]:
                    last_scraped[site_name] = ts

        has_data = [s for s in sites if last_scraped.get(s["name"])]
        never_scraped = [s for s in sites if not last_scraped.get(s["name"])]

        has_data.sort(key=lambda c: last_scraped.get(c["name"]) or "")

        merged = []
        hi, ni = 0, 0
        while hi < len(has_data) or ni < len(never_scraped):
            for _ in range(2):
                if hi < len(has_data):
                    merged.append(has_data[hi])
                    hi += 1
            if ni < len(never_scraped):
                merged.append(never_scraped[ni])
                ni += 1

        print("Sites priority order (interleaved staleness):")
        for s in merged[:12]:
            print(f"  {s['name']}: last scraped = {last_scraped.get(s['name']) or 'KABHI NAHI'}")
        return merged
    except Exception as e:
        print(f"[WARNING] Staleness sorting fail hui ({e}) - fixed order use kar rahe hain.")
        return sites


def run():
    summary = {"new": 0, "changed": 0, "unchanged": 0, "errors": 0}
    started = time.time()
    deadline = started + float(os.environ.get("MAX_RUN_MINUTES", "45")) * 60
    skipped_sites = []

    only_site_raw = os.environ.get("ONLY_SITE", "").strip()
    if only_site_raw:
        wanted = {s.strip() for s in only_site_raw.split(",") if s.strip()}
        sites = [s for s in SITES if s["name"] in wanted]
        missing = wanted - {s["name"] for s in sites}
        if missing:
            print(f"[WARNING] sites.py me nahi mile: {', '.join(missing)}")
        if not sites:
            print(f"[ERROR] ONLY_SITE='{only_site_raw}' - koi bhi site sites.py me nahi mili")
            return
    else:
        sites = get_staleness_order(filter_by_group(SITES))

    with sync_playwright() as p:
        for config in sites:
            if time.time() > deadline:
                skipped_sites.append(config["name"])
                continue
            print(f"\n=== Scraping: {config['name']} ===")
            try:
                if config.get("platform") == "shopify":
                    products = scrape_shopify(config)
                    print(f"  {config['domain']} -> {len(products)} products")
                elif config.get("use_scraperapi"):
                    products = scrape_site_scraperapi(config)
                elif config.get("use_firecrawl"):
                    products = scrape_site_firecrawl(config)
                elif config.get("use_scrapegraph"):
                    products = scrape_site_scrapegraph(config)
                else:
                    browser, context = build_browser_context(p, config)
                    page = context.new_page()
                    products = scrape_site(page, config)
                    browser.close()

                by_site = defaultdict(list)
                for product in products:
                    by_site[product.get("site") or config["name"]].append({**product, "site": product.get("site") or config["name"]})
                for site_products in by_site.values():
                    t0 = time.time()
                    try:
                        res = save_products(site_products, deadline=deadline + 5 * 60)
                    except Exception as e:
                        # batch fail (jaise ek kharab row se bulk insert) - purana per-product rasta, slow lekin sahi
                        print(f"  [WARN batch save fail, per-product fallback] {e}")
                        res = Counter()
                        for product in site_products:
                            try:
                                r = save_product(product)
                                res["new" if r == "new" else "unchanged" if r == "unchanged" else "changed"] += 1
                            except Exception as e2:
                                res["errors"] += 1
                                print(f"  [ERROR saving product] {e2}")
                    for k in ("new", "changed", "unchanged", "errors"):
                        summary[k] += res.get(k, 0)
                    details = {k: v for k, v in res.items() if k not in ("new", "changed", "unchanged") and v}
                    print(f"  saved in {time.time() - t0:.0f}s: new={res['new']} changed={res['changed']} "
                          f"unchanged={res['unchanged']} {details or ''}")

            except Exception as e:
                summary["errors"] += 1
                print(f"  [ERROR scraping site] {e}")

    print("\n=== Summary ===")
    print(summary)
    print(f"Run time: {(time.time() - started) / 60:.1f} min")
    if skipped_sites:
        # agla run staleness order se inhe pehle uthayega
        print(f"MAX_RUN_MINUTES khatam - {len(skipped_sites)} sites agli baar: {', '.join(skipped_sites)}")


if __name__ == "__main__":
    run()
