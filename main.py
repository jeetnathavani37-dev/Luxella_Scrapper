"""
Entry point. Ye script GitHub Actions se har 6 ghante chalega.

Local test ke liye:
    pip install -r requirements.txt
    patchright install chromium
    python main.py

Sirf kuch sites test karni ho (comma se separate karo):
    ONLY_SITE=michaelkors python main.py
    ONLY_SITE=michaelkors,coach python main.py

Proxy (Webshare rotating residential) ke liye ye GitHub Secrets chahiye:
    PROXY_SERVER    = http://p.webshare.io:80
    PROXY_USERNAME  = base username, bina country suffix ke (jaise: pkbqdwus)
    PROXY_PASSWORD  = proxy password

MK/Coach (Akamai-protected) ke liye ye GitHub Secret chahiye:
    SCRAPERAPI_KEY  = ScraperAPI dashboard se

Prompt-based extraction (selector-maintenance heavy sites) ke liye:
    SCRAPEGRAPH_API_KEY = ScrapeGraphAI dashboard se
    (config mein "use_scrapegraph": True, dekho scrapegraph_scraper.py)

NOTE (2026-08-29): Proxy sites ke liye images/fonts/media block kar diye
hain (sirf HTML/CSS/JS load hota hai) - isse proxy bandwidth ~70-80% tak
bach jaati hai. Product image URLs HTML attributes (src) se hi milte hain,
actual image bytes download karne ki zaroorat nahi thi scraping ke liye.

NOTE (2026-08-29) #2: Playwright se patchright pe switch kiya tha, lekin
Akamai ne patchright ko bhi 403 diya. Ab MK/Coach ScraperAPI (managed
anti-bot service) use karte hain instead - "use_scraperapi": True config
mein, dekho scraperapi_scraper.py. Proxy/browser wala code ab sirf
future ke liye rakha hai agar koi aur JS-heavy non-Akamai site add karni
ho (abhi koi site "needs_browser" use nahi kar rahi).

NOTE (2026-08-30): ScrapeGraphAI add kiya - prompt-based extraction,
CSS selectors ki zaroorat nahi. "use_scrapegraph": True config mein.
Akamai bypass ke liye nahi hai (uske liye ScraperAPI hi rahega) - ye
un sites ke liye hai jinke selectors baar baar todte/badalte hain.
"""
import os
import re
from patchright.sync_api import sync_playwright

from sites import SITES
from extract import scrape_site
from shopify_scraper import scrape_shopify
from scraperapi_scraper import scrape_site_scraperapi
from scrapegraph_scraper import scrape_site_scrapegraph
from db import save_product


def build_proxy_username(base_username, country):
    """
    Webshare rotating residential country-specific usernames use karta hai:
        {base}-{country}-{n}    jaise pkbqdwus-us-1, pkbqdwus-gb-1

    Agar galti se already suffix laga diya ho (pkbqdwus-gb-1),
    to usko hata ke sahi country lagate hain.
    """
    if not base_username:
        return base_username

    base = re.sub(r"-[a-z]{2}-\d+$", "", base_username.strip())

    if not country:
        return base

    return f"{base}-{country.lower()}-1"


def _block_heavy_resources(route):
    """Images/fonts/media block karo - bandwidth bachane ke liye (sirf proxy sites pe use hota hai)."""
    if route.request.resource_type in ("image", "media", "font"):
        route.abort()
    else:
        route.continue_()


def build_browser_context(playwright, config):
    """Agar site ko proxy chahiye to proxy ke saath browser banata hai, warna normal."""
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
            print(f"  [WARNING] {config['name']} ko proxy chahiye par PROXY_SERVER secret set nahi hai — "
                  f"is site pe block hone ka risk hai.")

    browser = playwright.chromium.launch(**launch_args)
    context = browser.new_context(
        viewport={"width": 1366, "height": 900},
        locale="en-US",
    )

    # Sirf proxy wali sites ke liye images/fonts/media block karo (bandwidth save)
    if needs_proxy:
        context.route("**/*", _block_heavy_resources)

    return browser, context


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
        sites = SITES

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
