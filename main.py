"""
Entry point. Ye script GitHub Actions se har 6 ghante chalega.

NOTE (2026-09-02): BADA fix - 90+ sites hain, 60-min timeout ke andar
saari scrape nahi ho paati. Pehle SITES list fixed order mein process
hoti thi - shuru wali sites hamesha scrape hoti thi, end wali (jaise
aloyoga) hamesha timeout se pehle chhoot jaati thi. Fix: ab Supabase se
har site ka last scraped_at fetch karke, sabse purana-scraped pehle
process karte hain - fair rotation, koi site permanently starve nahi
hoti.
"""
import os
import re
from collections import defaultdict
from patchright.sync_api import sync_playwright
from supabase import create_client

from sites import SITES
from extract import scrape_site
from shopify_scraper import scrape_shopify
from scraperapi_scraper import scrape_site_scraperapi
from scrapegraph_scraper import scrape_site_scrapegraph
from db import save_product


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
        resp = sb.table("products").select("site,scraped_at").execute()

        last_scraped = defaultdict(lambda: None)
        for row in resp.data:
            site_name = row.get("site")
            ts = row.get("scraped_at")
            if site_name and ts:
                if last_scraped[site_name] is None or ts > last_scraped[site_name]:
                    last_scraped[site_name] = ts

        def sort_key(config):
            ts = last_scraped.get(config["name"])
            return ts or ""

        sorted_sites = sorted(sites, key=sort_key)
        print("Sites priority order (staleness-based):")
        for s in sorted_sites[:10]:
            print(f"  {s['name']}: last scraped = {last_scraped.get(s['name']) or 'KABHI NAHI'}")
        return sorted_sites
    except Exception as e:
        print(f"[WARNING] Staleness sorting fail hui ({e}) - fixed order use kar rahe hain.")
        return sites


def run():
    summary = {"new": 0, "changed": 0, "unchanged": 0, "errors": 0}

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
        sites = get_staleness_order(SITES)

    with sync_playwright() as p:
        for config in sites:
            print(f"\n=== Scraping: {config['name']} ===")
            try:
                if config.get("platform") == "shopify":
                    products = scrape_shopify(config)
                    print(f"  {config['domain']} -> {len(products)} products")
                elif config.get("use_scraperapi"):
                    products = scrape_site_scraperapi(config)
                elif config.get("use_scrapegraph"):
                    products = scrape_site_scrapegraph(config)
                else:
                    browser, context = build_browser_context(p, config)
                    page = context.new_page()
                    products = scrape_site(page, config)
                    browser.close()

                for product in products:
                    try:
                        result = save_product(product)
                        if result == "new":
                            summary["new"] += 1
                        elif result == "unchanged":
                            summary["unchanged"] += 1
                        else:
                            summary["changed"] += 1
                            print(f"  CHANGE: {product.get('name')} -> {result}")
                    except Exception as e:
                        summary["errors"] += 1
                        print(f"  [ERROR saving product] {e}")

            except Exception as e:
                summary["errors"] += 1
                print(f"  [ERROR scraping site] {e}")

    print("\n=== Summary ===")
    print(summary)


if __name__ == "__main__":
    run()
