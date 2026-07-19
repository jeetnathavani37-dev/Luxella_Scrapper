"""
Entry point. Ye script GitHub Actions se har 6-12 ghante chalega.

Local test ke liye:
    pip install -r requirements.txt
    playwright install chromium
    python main.py
"""
import os
from playwright.sync_api import sync_playwright

from sites import SITES
from extract import scrape_site
from db import save_product


def build_browser_context(playwright, config):
    """Agar site ko proxy chahiye to proxy ke saath browser banata hai, warna normal."""
    launch_args = {"headless": True}

    if config.get("needs_proxy"):
        proxy_server = os.environ.get("PROXY_SERVER")   # e.g. "http://provider-host:port"
        proxy_user = os.environ.get("PROXY_USERNAME")
        proxy_pass = os.environ.get("PROXY_PASSWORD")
        if proxy_server:
            launch_args["proxy"] = {
                "server": proxy_server,
                "username": proxy_user,
                "password": proxy_pass,
            }
        else:
            print(f"  [WARNING] {config['name']} ko proxy chahiye par PROXY_SERVER secret set nahi hai — "
                  f"is site pe block hone ka risk hai.")

    browser = playwright.chromium.launch(**launch_args)
    context = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    return browser, context


def run():
    summary = {"new": 0, "changed": 0, "unchanged": 0, "errors": 0}

    with sync_playwright() as p:
        for config in SITES:
            print(f"\n=== Scraping: {config['name']} ===")
            try:
                browser, context = build_browser_context(p, config)
                page = context.new_page()

                products = scrape_site(page, config)

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

                browser.close()
            except Exception as e:
                summary["errors"] += 1
                print(f"  [ERROR scraping site] {e}")

    print("\n=== Summary ===")
    print(summary)


if __name__ == "__main__":
    run()
