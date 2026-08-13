"""
Entry point. Ye script GitHub Actions se har 6 ghante chalega.

Local test ke liye:
    pip install -r requirements.txt
    playwright install chromium
    python main.py

Sirf ek site test karni ho:
    ONLY_SITE=michaelkors python main.py

Proxy (Webshare rotating residential) ke liye ye GitHub Secrets chahiye:
    PROXY_SERVER    = http://p.webshare.io:80
    PROXY_USERNAME  = base username, bina country suffix ke (jaise: pkbqdwus)
    PROXY_PASSWORD  = proxy password
"""
import os
import re
from playwright.sync_api import sync_playwright

from sites import SITES
from extract import scrape_site
from shopify_scraper import scrape_shopify
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

    # existing -xx-N suffix strip karo
    base = re.sub(r"-[a-z]{2}-\d+$", "", base_username.strip())

    if not country:
        return base

    return f"{base}-{country.lower()}-1"


def build_browser_context(playwright, config):
    """Agar site ko proxy chahiye to proxy ke saath browser banata hai, warna normal."""
    launch_args = {"headless": True}

    if config.get("needs_proxy"):
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

    launch_args["args"] = ["--disable-blink-features=AutomationControlled"]

    browser = playwright.chromium.launch(**launch_args)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        viewport={"width": 1366, "height": 900},
        locale="en-US",
        extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
    )
    context.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    )
    return browser, context


def run():
    summary = {"new": 0, "changed": 0, "unchanged": 0, "errors": 0}

    only_site = os.environ.get("ONLY_SITE")
    sites = [s for s in SITES if s["name"] == only_site] if only_site else SITES
    if only_site and not sites:
        print(f"[ERROR] ONLY_SITE='{only_site}' sites.py me nahi mila")
        return

    with sync_playwright() as p:
        for config in sites:
            print(f"\n=== Scraping: {config['name']} ===")
            try:
                if config.get("platform") == "shopify":
                    # halka rasta - koi browser/proxy nahi chahiye
                    products = scrape_shopify(config)
                    print(f"  {config['domain']} -> {len(products)} products")
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
