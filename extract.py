"""
Ek page se products nikalne ka core logic.
MK par jo Apify me test kiya tha, wahi logic yaha Playwright (Python) me hai.
"""
import re
import time
from datetime import datetime, timezone


def to_num(text):
    """'$199.50' -> 199.5, None agar number na mile"""
    if not text:
        return None
    match = re.search(r"[\d,]+\.?\d*", text.replace(",", ""))
    return float(match.group()) if match else None


def click_load_more_and_scroll(page, load_more_selector, max_clicks=15):
    """Load More button ko baar baar click karta hai, warna scroll karta hai,
    taaki poori category ke products load ho jaayein (lazy-loading sites ke liye).

    document.body kabhi kabhi null hota hai (page abhi poora load nahi hua,
    ya proxy/Akamai ne khaali interstitial page bheja) — ab isse crash nahi
    hota, scroll bas skip ho jaata hai.
    """
    for _ in range(max_clicks):
        clicked = False
        if load_more_selector:
            try:
                btn = page.locator(load_more_selector).first
                if btn.is_visible(timeout=1000):
                    btn.click()
                    clicked = True
                    time.sleep(2.5)
            except Exception:
                pass
        if not clicked:
            try:
                did_scroll = page.evaluate(
                    "() => { if (document.body) { "
                    "window.scrollBy(0, document.body.scrollHeight); return true; "
                    "} return false; }"
                )
                if not did_scroll:
                    # body hi nahi hai - is page pe aur scroll karna bekaar hai
                    break
            except Exception as e:
                print(f"    [WARN] scroll failed: {e}")
                break
            time.sleep(1.2)
    time.sleep(2)


def extract_products(page, config):
    """Config ke selectors use karke current page se saare products nikaalta hai."""
    tiles = page.query_selector_all(config["tile_selector"])
    results = []

    for tile in tiles:
        name_el = tile.query_selector(config["name_selector"])
        price_el = tile.query_selector(config["price_selector"])
        link_el = tile.query_selector(config["link_selector"])
        img_el = tile.query_selector("img")

        name = name_el.inner_text().strip() if name_el else None
        price_raw = price_el.inner_text().strip() if price_el else None
        product_url = link_el.get_attribute("href") if link_el else None
        if product_url and product_url.startswith("/"):
            product_url = page.url.split("/", 3)[0] + "//" + page.url.split("/", 3)[2] + product_url

        sku = tile.get_attribute("data-pid")
        if not sku and product_url:
            m = re.search(r"/([A-Z0-9]{6,})\.html", product_url, re.I)
            sku = m.group(1) if m else None

        image_url = None
        if img_el:
            src = img_el.get_attribute("src") or ""
            data_src = img_el.get_attribute("data-src") or ""
            if data_src and not data_src.startswith("data:"):
                image_url = data_src
            elif src and not src.startswith("data:"):
                image_url = src

        if not (name or sku):
            continue

        results.append({
            "sku": sku,
            "name": name,
            "price": to_num(price_raw),
            "in_stock": True,
            "product_url": product_url,
            "image_url": image_url,
            "currency": config.get("currency", "USD"),
        })

    return results


def scrape_site(page, config):
    """Ek site ke saare start_urls scrape karta hai, poori product list return karta hai."""
    all_products = []
    for url in config["start_urls"]:
        try:
            response = page.goto(url, wait_until="networkidle", timeout=60000)
        except Exception as e:
            print(f"  [ERROR] goto failed for {url}: {e}")
            continue

        # Diagnostic: pata karo actually kis page pe pahunche (redirect / block / interstitial)
        final_url = page.url
        status = response.status if response else None
        title = page.title()
        if final_url != url or (status and status >= 400):
            print(f"  [DEBUG] requested: {url}")
            print(f"  [DEBUG] landed on: {final_url} (status={status}, title='{title}')")

        click_load_more_and_scroll(page, config.get("load_more_selector"))
        products = extract_products(page, config)

        if len(products) == 0:
            tile_count = len(page.query_selector_all(config["tile_selector"]))
            body_snippet = page.inner_text("body")[:200].replace("\n", " ") if page.query_selector("body") else "(no body found)"
            print(f"  [DEBUG] page title: {title}")
            print(f"  [DEBUG] tile_selector matches: {tile_count}")
            print(f"  [DEBUG] body text starts with: {body_snippet}")

        for p in products:
            p["site"] = config["name"]
            p["category"] = "uncategorized"
            p["brand"] = config["name"]
            p["scraped_at"] = datetime.now(timezone.utc).isoformat()
        all_products.extend(products)
        print(f"  {url} -> {len(products)} products")
    return all_products
